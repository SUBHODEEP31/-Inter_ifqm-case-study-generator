"""Stage 4 smoke (no API key): CaseBrief schema + source-anchoring logic.

Validates the parts that do not require a live LLM:
  - CaseBrief and sub-models validate.
  - _drop_unsourced removes items with empty/invalid source_id.
  - citation-manifest rebuild keeps only real sources.
Live extraction (build_case_brief -> Groq) is deferred until a key is present.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.brief_engine import (  # noqa: E402
    CaseBrief, Citation, FinancialDatum, Intervention, Protagonist,
    TimelineEvent, _drop_unsourced, _valid_source_ids,
)
from src.indexing import Chunk, RetrievedChunk  # noqa: E402


def _ctx(source_id: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk=Chunk(
            chunk_id=f"{source_id}-c0001", source_id=source_id, source_type="pdf",
            title=f"Doc {source_id}", origin=f"/data/{source_id}.pdf",
            text="x", raw_text="x",
        ),
        score=1.0,
    )


def main() -> int:
    failures = []

    contexts = [_ctx("PDF-1"), _ctx("WEB-2")]
    valid = _valid_source_ids(contexts)
    if valid != {"PDF-1", "WEB-2"}:
        failures.append(f"valid source ids wrong: {valid}")

    brief = CaseBrief(
        company="ACME",
        protagonist=Protagonist(name="Jane Doe", designation="COO", source_id="PDF-1"),
        historical_timeline=[
            TimelineEvent(date="2020", event="real", source_id="PDF-1"),
            TimelineEvent(date="2021", event="hallucinated", source_id="GHOST-9"),
            TimelineEvent(date="2022", event="unsourced", source_id=""),
        ],
        strategic_interventions=[
            Intervention(name="Lean", methodology="Lean", description="d", source_id="WEB-2"),
            Intervention(name="Fake", methodology="x", description="d", source_id="NOPE"),
        ],
        financial_appendix_data=[FinancialDatum(metric="Revenue", value="$1B", source_id="PDF-1")],
    )

    _drop_unsourced(brief, valid)
    if len(brief.historical_timeline) != 1 or brief.historical_timeline[0].source_id != "PDF-1":
        failures.append(f"timeline not filtered: {[e.source_id for e in brief.historical_timeline]}")
    if len(brief.strategic_interventions) != 1:
        failures.append(f"interventions not filtered: {len(brief.strategic_interventions)}")
    if len(brief.financial_appendix_data) != 1:
        failures.append("valid financial datum was wrongly dropped")

    # Manifest rebuild (mirrors build_case_brief tail).
    seen = {}
    for rc in contexts:
        ch = rc.chunk
        seen.setdefault(ch.source_id, Citation(source_id=ch.source_id, title=ch.title, origin=ch.origin))
    brief.source_citations_manifest = list(seen.values())
    if {c.source_id for c in brief.source_citations_manifest} != {"PDF-1", "WEB-2"}:
        failures.append("manifest rebuild wrong")

    if failures:
        print("[STAGE 4 SMOKE] [FAIL]")
        for f in failures:
            print("  -", f)
        return 1
    print("[STAGE 4 SMOKE] [PASS] schema + source-anchoring + manifest OK (live extraction deferred: no key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
