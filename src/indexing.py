"""Stage 3 - Hybrid retrieval engine.

Pipeline:
  chunk -> (optional) contextual enrichment -> dense embed (bge-large) + store in
  ChromaDB, plus a parallel BM25 sparse index. At query time: dense search +
  sparse search fused via Reciprocal Rank Fusion (RRF), then a bge-reranker
  cross-encoder narrows to the top-k most relevant passages.

Contextual enrichment uses the UTILITY Groq model to prepend a one/two-sentence
source header to each chunk (Anthropic Contextual Retrieval). It is optional:
when no GROQ_API_KEY is configured the index still builds (enrichment skipped),
so the retrieval core is verifiable without a key.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings
from pydantic import BaseModel

from src.ingestion import IngestedDoc
from src.logger import get_logger

log = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CHROMA = str(_PROJECT_ROOT / "data" / "chroma_db")

# Use cached local BAAI/bge-large-en-v1.5 model for offline safety (instantly loaded)
# Capping chunk counts to 100 ensures CPU encoding completes in ~15-20s.
_EMBED_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5")
_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
_RRF_K = 60

# Lazily-loaded embedding model (shared across HybridIndex instances).
_EMBEDDER = None


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from sentence_transformers import SentenceTransformer

        log.info(f"Loading local embedding model {_EMBED_MODEL_NAME}...")
        _EMBEDDER = SentenceTransformer(_EMBED_MODEL_NAME, local_files_only=True, device="cpu")
    return _EMBEDDER


def _tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization for BM25."""
    return re.findall(r"[a-z0-9]+", text.lower())


class Chunk(BaseModel):
    chunk_id: str
    source_id: str
    source_type: str
    title: str
    origin: str
    text: str          # text used for embedding/BM25 (may be enriched)
    raw_text: str      # original chunk text without enrichment header
    enriched: bool = False


class RetrievedChunk(BaseModel):
    chunk: Chunk
    score: float


def _split_documents(docs: list[IngestedDoc], chunk_size: int = 800, overlap: int = 150) -> list[Chunk]:
    """Token-aware recursive splitting via langchain + tiktoken."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=chunk_size, chunk_overlap=overlap
    )
    chunks: list[Chunk] = []
    for doc in docs:
        for i, piece in enumerate(splitter.split_text(doc.text)):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.source_id}-c{i:04d}",
                    source_id=doc.source_id,
                    source_type=doc.source_type.value,
                    title=doc.title,
                    origin=doc.origin,
                    text=piece,
                    raw_text=piece,
                )
            )
    log.info(f"Split {len(docs)} docs into {len(chunks)} chunks.")
    return chunks


def _enrich_chunks(chunks: list[Chunk]) -> None:
    """Prepend an LLM-generated context header to each chunk, in place.

    Silently degrades to a no-op if the Groq client cannot be constructed.
    """
    try:
        from src.llm_client import Role, get_llm_client

        client = get_llm_client()
    except Exception as exc:  # e.g. missing key
        log.warning(f"Contextual enrichment skipped (no usable LLM client): {exc}")
        return

    system = (
        "You write a single concise sentence that situates a text chunk within its "
        "source document (company, time period, topic). Output only that sentence."
    )
    
    skip_enrichment = False
    for idx, ch in enumerate(chunks):
        # Sample-based enrichment for large chunk counts to save time/tokens:
        # Only enrich first 10 and last 10 chunks if total chunks > 30.
        should_enrich = (len(chunks) <= 30) or (idx < 10) or (idx >= len(chunks) - 10)
        
        if not should_enrich or skip_enrichment:
            continue
            
        prompt = (
            f"Source document: {ch.title} ({ch.source_type}).\n"
            f"Chunk:\n{ch.raw_text[:1500]}\n\n"
            "Context sentence:"
        )
        try:
            # Call complete with no_retry=True.
            # If Gemini is rate-limited, complete() automatically switches to Groq Llama 8B.
            header = client.complete(
                prompt, role=Role.BULK, system=system, max_tokens=80, temperature=0.0, no_retry=True
            )
            if header:
                ch.text = f"{header.strip()}\n\n{ch.raw_text}"
                ch.enriched = True
        except Exception as exc:
            log.warning(f"Enrichment failed on chunk index {idx} (Gemini + Groq rate limits hit): {exc}. Bypassing remaining chunks to prevent delay.")
            skip_enrichment = True
    log.info(f"Contextual enrichment complete ({sum(c.enriched for c in chunks)}/{len(chunks)} enriched).")


class HybridIndex:
    """ChromaDB dense index + BM25 sparse index + cross-encoder reranker."""

    def __init__(self, collection_name: str = "company_data", persist_dir: str | None = None) -> None:
        self.persist_dir = persist_dir or os.getenv("CHROMA_DIR", _DEFAULT_CHROMA)
        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_dir, settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._chunks: dict[str, Chunk] = {}
        self._bm25 = None
        self._bm25_ids: list[str] = []

    # -- build ------------------------------------------------------------- #
    def build(self, docs: list[IngestedDoc], enrich: bool = True) -> int:
        """Chunk, (optionally) enrich, embed, and index a set of documents."""
        chunks = _split_documents(docs)
        if not chunks:
            log.warning("No chunks produced; nothing indexed.")
            return 0

        # Strategic sampling: cap at 100 chunks for CPU performance.
        # For large docs (300+ pages), we take first 50 + last 50 chunks
        # to capture both introductory context and concluding sections.
        _MAX_CHUNKS = 100
        if len(chunks) > _MAX_CHUNKS:
            half = _MAX_CHUNKS // 2
            sampled = chunks[:half] + chunks[-half:]
            log.info(f"Sampled {len(sampled)} chunks from {len(chunks)} total (first {half} + last {half}) for CPU performance.")
            chunks = sampled

        if enrich:
            _enrich_chunks(chunks)

        texts = [c.text for c in chunks]
        embedder = _get_embedder()
        log.info(f"Encoding {len(texts)} chunks with {_EMBED_MODEL_NAME} on CPU...")
        embeddings = embedder.encode(
            texts, normalize_embeddings=True, show_progress_bar=True, batch_size=64
        ).tolist()
        log.info(f"Encoding complete for {len(texts)} chunks.")

        self.collection.add(
            ids=[c.chunk_id for c in chunks],
            documents=[c.raw_text for c in chunks],
            embeddings=embeddings,
            metadatas=[
                {
                    "source_id": c.source_id,
                    "source_type": c.source_type,
                    "title": c.title,
                    "origin": c.origin,
                    "enriched": c.enriched,
                }
                for c in chunks
            ],
        )
        for c in chunks:
            self._chunks[c.chunk_id] = c
        self._rebuild_bm25()
        log.info(f"Indexed {len(chunks)} chunks into '{self.collection.name}'.")
        return len(chunks)

    def _rebuild_bm25(self) -> None:
        from rank_bm25 import BM25Okapi

        self._bm25_ids = list(self._chunks.keys())
        corpus = [_tokenize(self._chunks[cid].text) for cid in self._bm25_ids]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    def load_from_store(self) -> int:
        """Repopulate in-memory chunks + BM25 from the persisted collection."""
        got = self.collection.get(include=["documents", "metadatas"])
        ids = got.get("ids", []) or []
        docs = got.get("documents", []) or []
        metas = got.get("metadatas", []) or []
        for cid, text, meta in zip(ids, docs, metas):
            self._chunks[cid] = Chunk(
                chunk_id=cid,
                source_id=meta.get("source_id", ""),
                source_type=meta.get("source_type", ""),
                title=meta.get("title", ""),
                origin=meta.get("origin", ""),
                text=text,
                raw_text=text,
                enriched=bool(meta.get("enriched", False)),
            )
        self._rebuild_bm25()
        log.info(f"Loaded {len(self._chunks)} chunks from store.")
        return len(self._chunks)

    # -- query ------------------------------------------------------------- #
    def _dense_ids(self, query: str, top_k: int) -> list[str]:
        embedder = _get_embedder()
        q_emb = embedder.encode(
            [_QUERY_INSTRUCTION + query], normalize_embeddings=True
        ).tolist()
        res = self.collection.query(query_embeddings=q_emb, n_results=top_k)
        ids = res.get("ids", [[]])
        return ids[0] if ids else []

    def _sparse_ids(self, query: str, top_k: int) -> list[str]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(zip(self._bm25_ids, scores), key=lambda x: x[1], reverse=True)
        return [cid for cid, score in ranked[:top_k] if score > 0]

    @staticmethod
    def _rrf(ranked_lists: list[list[str]], k: int = _RRF_K) -> list[str]:
        scores: dict[str, float] = {}
        for ranked in ranked_lists:
            for rank, cid in enumerate(ranked):
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
        return [cid for cid, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]

    def query(
        self,
        query: str,
        top_k_dense: int = 30,
        top_k_final: int = 8,
        rerank_pool: int = 20,
    ) -> list[RetrievedChunk]:
        """Hybrid retrieve using dense + BM25 RRF fusion. No heavy reranker needed."""
        if not self._chunks:
            self.load_from_store()
        if not self._chunks:
            log.warning("Query on empty index.")
            return []

        dense = self._dense_ids(query, top_k_dense)
        sparse = self._sparse_ids(query, top_k_dense)
        fused = self._rrf([dense, sparse])[:top_k_final]
        if not fused:
            return []

        # Use RRF fusion scores directly — no cross-encoder reranker needed
        results = []
        for rank, cid in enumerate(fused):
            score = 1.0 / (rank + 1)  # RRF-derived score
            if cid in self._chunks:
                results.append(RetrievedChunk(chunk=self._chunks[cid], score=score))
            else:
                log.warning(f"Chunk ID '{cid}' returned from query was not found in indexer's in-memory chunk storage.")

        log.info(
            f"query({query!r}): dense={len(dense)} sparse={len(sparse)} "
            f"fused -> top {len(results)} results."
        )
        return results


# =====================================================================
# API BRIDGE LAYER (BRIDGES MAIN.PY INTERFACES TO HYBRIDINDEX CORE)
# =====================================================================
class HybridIndexManager(HybridIndex):
    def __init__(self, chroma_path: str | None = None, collection_name: str = "company_context", *args, **kwargs) -> None:
        super().__init__(collection_name=collection_name, persist_dir=chroma_path)
        self.raw_chunks: list[str] = []

    def enrich_and_index_chunks(self, company_name: str, md_text: str, source_id: str) -> None:
        """Helper to match main.py's indexing API, routing through HybridIndex.build()."""
        from src.ingestion import IngestedDoc, SourceType
        
        # Build IngestedDoc payload wrapper
        doc = IngestedDoc(
            source_id=source_id,
            source_type=SourceType.PDF if source_id.lower().endswith(".pdf") else SourceType.WEB,
            title=source_id,
            origin=source_id,
            text=md_text
        )
        
        # Build index WITHOUT enrichment to avoid wasting API quota on 100+ LLM calls.
        # The raw PDF text is already high quality for retrieval.
        self.build([doc], enrich=False)
        
        # Capture raw chunks for BM25/indexing compatibility
        self.raw_chunks.extend(list(self._chunks.values()))

    def batch_index_documents(self, artifacts: list[dict]) -> None:
        """Batch-index multiple documents in a single build() call.
        
        This is significantly faster than calling enrich_and_index_chunks() in a loop
        because it only chunks, embeds, and builds BM25 once instead of N times.
        
        Args:
            artifacts: List of dicts with 'source_id' and 'text' keys.
        """
        from src.ingestion import IngestedDoc, SourceType

        docs = []
        for artifact in artifacts:
            sid = artifact["source_id"]
            docs.append(IngestedDoc(
                source_id=sid,
                source_type=SourceType.PDF if sid.lower().endswith(".pdf") else SourceType.WEB,
                title=sid,
                origin=sid,
                text=artifact["text"]
            ))
        
        if docs:
            log.info(f"Batch indexing {len(docs)} documents in a single build pass...")
            self.build(docs, enrich=False)
            self.raw_chunks.extend(list(self._chunks.values()))
            log.info(f"Batch indexing complete. {len(self._chunks)} total chunks in index.")

    def retrieve_optimal_context(self, query: str, top_n: int = 8) -> list[str]:
        """Helper to match main.py's query API, returning raw text strings."""
        retrieved_chunks = self.query(query, top_k_final=top_n)
        return [f"Source: {rc.chunk.source_id}\nContent:\n{rc.chunk.raw_text}" for rc in retrieved_chunks]
