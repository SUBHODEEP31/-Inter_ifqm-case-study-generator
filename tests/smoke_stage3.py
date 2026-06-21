"""Stage 3 smoke test - run with the project venv:

    D:\\ifqm-case-generator\\.venv\\Scripts\\python.exe tests\\smoke_stage3.py

Verifies (no Groq key required; enrichment disabled):
  1. A HybridIndex builds (chunk -> bge-large embed -> ChromaDB + BM25).
  2. A topical query returns 1..8 reranked chunks.
  3. The top-ranked chunk comes from the topically-correct source document
     (i.e. dense+sparse+rerank actually discriminate relevance).

First run downloads bge-large-en-v1.5 and bge-reranker-v2-m3 (~3.5GB).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.indexing import HybridIndex  # noqa: E402
from src.ingestion import IngestedDoc, SourceType  # noqa: E402

COLLECTION = "smoke_stage3"

DOCS = [
    IngestedDoc(
        source_id="DOC-QUALITY",
        source_type=SourceType.WEB,
        title="Quality program",
        origin="https://example.com/quality",
        text=(
            "The steel plant deployed Lean Six Sigma and Total Quality Management to cut "
            "defects. A DMAIC project reduced slab rejection rates by 38 percent over two "
            "years. Kaizen circles and statistical process control charts were used on the "
            "hot strip mill to stabilize thickness tolerance and improve first-pass yield."
        ),
    ),
    IngestedDoc(
        source_id="DOC-FINANCE",
        source_type=SourceType.WEB,
        title="Financials",
        origin="https://example.com/finance",
        text=(
            "Consolidated revenue rose to 2.4 lakh crore rupees, with EBITDA margin of 18 "
            "percent. The balance sheet showed net debt reduction and improved return on "
            "capital employed. Earnings per share grew year over year on stronger volumes."
        ),
    ),
    IngestedDoc(
        source_id="DOC-UNRELATED",
        source_type=SourceType.WEB,
        title="Cooking",
        origin="https://example.com/cooking",
        text=(
            "To make a classic risotto, toast arborio rice in butter, then add warm stock "
            "one ladle at a time, stirring until creamy. Finish with parmesan and a "
            "squeeze of lemon. Rest briefly before serving."
        ),
    ),
]


def main() -> int:
    print("=== Stage 3 smoke test ===")

    idx = HybridIndex(collection_name=COLLECTION)
    try:
        idx._client.delete_collection(COLLECTION)  # fresh start on rerun
    except Exception:
        pass
    idx = HybridIndex(collection_name=COLLECTION)

    n = idx.build(DOCS, enrich=False)
    build_ok = n > 0
    print(f"[{'PASS' if build_ok else 'FAIL'}] indexed {n} chunks (bge-large + BM25)")

    query = "Six Sigma quality improvement and defect reduction at the steel plant"
    results = idx.query(query, top_k_final=8)
    count_ok = 1 <= len(results) <= 8
    print(f"[{'PASS' if count_ok else 'FAIL'}] query returned {len(results)} reranked chunks (need 1..8)")

    top_source = results[0].chunk.source_id if results else None
    relevance_ok = top_source == "DOC-QUALITY"
    print(f"[{'PASS' if relevance_ok else 'FAIL'}] top chunk source = {top_source} (expected DOC-QUALITY)")
    for r in results[:3]:
        print(f"        {r.chunk.source_id} score={r.score:.3f}")

    # cleanup
    try:
        idx._client.delete_collection(COLLECTION)
    except Exception:
        pass

    print("=" * 32)
    if build_ok and count_ok and relevance_ok:
        print("STAGE 3 SMOKE: PASS")
        return 0
    print("STAGE 3 SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
