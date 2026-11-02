"""Stage 2 smoke test - run with the project venv:

    D:\\ifqm-case-generator\\.venv\\Scripts\\python.exe tests\\smoke_stage2.py [company]

Verifies (no Groq key required):
  1. ddgs search returns >= 5 unique URLs for the target company.
  2. Crawl4AI successfully crawls at least one of those URLs into real Markdown.
  3. If a PDF exists in data/uploads, Docling parses it into non-empty Markdown.

The PDF check is reported as BLOCKED (not failed) when no PDF is present.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion import crawl_urls, parse_pdf, search_web  # noqa: E402

UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"


def check_search_and_crawl(company: str) -> bool:
    queries = [
        f"{company} company overview",
        f"{company} quality management OR operations strategy",
        f"{company} latest news",
    ]
    seen: dict[str, str] = {}
    for q in queries:
        for hit in search_web(q, max_results=8):
            seen.setdefault(hit["url"], hit["title"])

    url_count = len(seen)
    search_ok = url_count >= 5
    print(f"[{'PASS' if search_ok else 'FAIL'}] ddgs returned {url_count} unique URLs (need >=5)")

    urls = list(seen)[:3]
    crawled = crawl_urls(urls)
    substantial = {u: t for u, t in crawled.items() if len(t) > 500}
    crawl_ok = len(substantial) >= 1
    print(f"[{'PASS' if crawl_ok else 'FAIL'}] crawled {len(substantial)}/{len(urls)} URLs into >500-char Markdown")
    for u, t in substantial.items():
        print(f"        - {u} ({len(t)} chars)")
    return search_ok and crawl_ok


def check_pdf() -> bool:
    pdfs = sorted(UPLOAD_DIR.glob("*.pdf"))
    if not pdfs:
        print("[BLOCKED] No PDF in data/uploads - drop one there to verify PyMuPDF parsing.")
        return True  # not a failure
    doc = parse_pdf(pdfs[0])
    ok = len(doc.text) > 200
    print(f"[{'PASS' if ok else 'FAIL'}] PyMuPDF parsed {pdfs[0].name}: {len(doc.text)} chars")
    return ok


def main() -> int:
    company = sys.argv[1] if len(sys.argv) > 1 else "Tata Steel"
    print(f"=== Stage 2 smoke test (company={company!r}) ===")
    checks = [check_search_and_crawl(company), check_pdf()]
    print("=" * 32)
    if all(checks):
        print("STAGE 2 SMOKE: PASS")
        return 0
    print("STAGE 2 SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
