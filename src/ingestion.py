"""Stage 2 - Multimodal ingestion engine.

Three capabilities, matching the brief:
  * PDF parsing via IBM Docling -> layout-aware Markdown (multi-column text,
    nested tables, headings preserved).
  * Web discovery via ddgs (the renamed duckduckgo-search) -> candidate URLs for
    real-time brand/news context from a company keyword.
  * Async clean crawling via Crawl4AI (Playwright) -> ad/nav/boilerplate-stripped
    Markdown for each discovered URL.

Everything is normalized into `IngestedDoc` objects carrying a stable `source_id`
so later stages can enforce citation traceability. No LLM calls happen here, so
this stage is verifiable without a Groq key.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import ftfy
from pydantic import BaseModel, Field

from src.logger import get_logger

log = get_logger(__name__)


class SourceType(str, Enum):
    PDF = "pdf"
    WEB = "web"


class IngestedDoc(BaseModel):
    """A single ingested source document (PDF page-set or crawled web page)."""

    source_id: str
    source_type: SourceType
    title: str
    origin: str  # absolute file path or URL
    text: str  # Markdown / clean text
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    char_count: int = 0

    def model_post_init(self, _ctx) -> None:  # pydantic v2 hook
        if not self.char_count:
            self.char_count = len(self.text)


def _clean_text(text: str) -> str:
    """Fix mojibake/unicode issues and normalize whitespace."""
    if not text:
        return ""
    fixed = ftfy.fix_text(text)
    # Collapse runs of blank lines while preserving paragraph breaks.
    lines = [ln.rstrip() for ln in fixed.splitlines()]
    cleaned: list[str] = []
    blank = False
    for ln in lines:
        if ln.strip():
            cleaned.append(ln)
            blank = False
        elif not blank:
            cleaned.append("")
            blank = True
    return "\n".join(cleaned).strip()


# --------------------------------------------------------------------------- #
# PDF parsing (Docling)
# --------------------------------------------------------------------------- #
_CONVERTER = None


def _get_converter():
    """Lazily construct a Docling DocumentConverter (first call is slow)."""
    global _CONVERTER
    if _CONVERTER is None:
        from docling.document_converter import DocumentConverter

        _CONVERTER = DocumentConverter()
        log.info("Docling DocumentConverter initialized.")
    return _CONVERTER


def parse_pdf(pdf_path: str | Path, source_id: str | None = None) -> IngestedDoc:
    """Parse a PDF into layout-aware Markdown using Docling."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    log.info(f"Parsing PDF via Docling: {path.name}")
    converter = _get_converter()
    result = converter.convert(str(path))
    markdown = _clean_text(result.document.export_to_markdown())
    log.info(f"Docling parsed {path.name}: {len(markdown)} chars of Markdown.")

    return IngestedDoc(
        source_id=source_id or f"PDF-{path.stem}",
        source_type=SourceType.PDF,
        title=path.name,
        origin=str(path),
        text=markdown,
    )


# --------------------------------------------------------------------------- #
# Web search (ddgs)
# --------------------------------------------------------------------------- #
def search_web(query: str, max_results: int = 8) -> list[dict[str, str]]:
    """Return normalized search hits: [{title, url, snippet}, ...]."""
    from ddgs import DDGS

    log.info(f"Web search (ddgs): {query!r} (max_results={max_results})")
    hits: list[dict[str, str]] = []
    with DDGS() as ddgs:
        for raw in ddgs.text(query, max_results=max_results):
            url = raw.get("href") or raw.get("url") or ""
            if not url:
                continue
            hits.append(
                {
                    "title": raw.get("title", "").strip(),
                    "url": url,
                    "snippet": (raw.get("body") or raw.get("snippet") or "").strip(),
                }
            )
    log.info(f"ddgs returned {len(hits)} usable hits for {query!r}")
    return hits


# --------------------------------------------------------------------------- #
# Async crawling (Crawl4AI / Playwright)
# --------------------------------------------------------------------------- #
def _extract_markdown(result) -> str:
    """Pull clean Markdown out of a Crawl4AI result across API variants."""
    md = getattr(result, "markdown", None)
    if md is None:
        return _clean_text(getattr(result, "cleaned_html", "") or "")
    # crawl4ai may return a MarkdownGenerationResult or a plain string.
    raw = getattr(md, "fit_markdown", None) or getattr(md, "raw_markdown", None) or str(md)
    return _clean_text(raw)


async def _crawl_async(urls: list[str]) -> dict[str, str]:
    """Crawl each URL once, returning {url: clean_markdown} for successes."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    from crawl4ai.async_configs import CacheMode

    out: dict[str, str] = {}
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        excluded_tags=["nav", "footer", "aside", "header", "form"],
        word_count_threshold=20,
        page_timeout=45_000,
    )
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for url in urls:
            try:
                result = await crawler.arun(url=url, config=run_cfg)
                if getattr(result, "success", False):
                    text = _extract_markdown(result)
                    if text:
                        out[url] = text
                        log.info(f"Crawled OK ({len(text)} chars): {url}")
                    else:
                        log.warning(f"Crawled but empty content: {url}")
                else:
                    log.warning(f"Crawl failed: {url} ({getattr(result, 'error_message', 'unknown')})")
            except Exception as exc:
                log.warning(f"Crawl exception for {url}: {type(exc).__name__}: {exc}")
    return out


def crawl_urls(urls: list[str]) -> dict[str, str]:
    """Synchronous wrapper around the async crawler."""
    if not urls:
        return {}
    return asyncio.run(_crawl_async(urls))


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
class IngestionResult(BaseModel):
    company: str
    docs: list[IngestedDoc]

    @property
    def web_docs(self) -> list[IngestedDoc]:
        return [d for d in self.docs if d.source_type == SourceType.WEB]

    @property
    def pdf_docs(self) -> list[IngestedDoc]:
        return [d for d in self.docs if d.source_type == SourceType.PDF]


def gather_web_context(company: str, max_results: int = 8, max_crawl: int = 6) -> list[IngestedDoc]:
    """Search for company context, crawl the top hits, return ingested web docs."""
    queries = [
        f"{company} company overview",
        f"{company} quality management OR operations strategy",
        f"{company} latest news",
    ]
    seen: set[str] = set()
    ranked: list[dict[str, str]] = []
    for q in queries:
        for hit in search_web(q, max_results=max_results):
            if hit["url"] not in seen:
                seen.add(hit["url"])
                ranked.append(hit)

    to_crawl = [h["url"] for h in ranked[:max_crawl]]
    crawled = crawl_urls(to_crawl)

    docs: list[IngestedDoc] = []
    for i, hit in enumerate(ranked):
        url = hit["url"]
        body = crawled.get(url) or hit["snippet"]
        if not body:
            continue
        docs.append(
            IngestedDoc(
                source_id=f"WEB-{i:03d}",
                source_type=SourceType.WEB,
                title=hit["title"] or urlparse(url).netloc,
                origin=url,
                text=body,
            )
        )
    log.info(f"gather_web_context produced {len(docs)} web docs for {company!r}")
    return docs


def ingest(
    company: str,
    pdf_paths: list[str | Path] | None = None,
    max_results: int = 8,
    max_crawl: int = 6,
) -> IngestionResult:
    """Full Stage 2 ingestion: parse PDFs + gather/crawl web context."""
    docs: list[IngestedDoc] = []

    for idx, pdf in enumerate(pdf_paths or []):
        try:
            docs.append(parse_pdf(pdf, source_id=f"PDF-{idx:03d}"))
        except Exception as exc:
            log.error(f"Failed to parse PDF {pdf}: {type(exc).__name__}: {exc}")

    docs.extend(gather_web_context(company, max_results=max_results, max_crawl=max_crawl))
    return IngestionResult(company=company, docs=docs)
