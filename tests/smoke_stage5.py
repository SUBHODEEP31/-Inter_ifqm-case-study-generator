"""Stage 5 smoke: generator structural checks + reference style index build.

No API key required:
  - generator imports; section blueprint is well-formed (10 unique sections).
  - banned-word detector flags filler.
  - CaseStudyDraft.full_text / word_count work.
  - reference_index builds the 'reference_cases' Chroma collection from the
    curated PDFs (dedups the identical Tesla copies) and returns a style
    exemplar via get_style_example.
Live generation (generate_case_study -> Groq) is deferred until a key is present.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generator import (  # noqa: E402
    BANNED_WORDS, CaseStudyDraft, Section, _SECTION_SPECS, _banned_hits,
)
from src.reference_index import build_reference_index, get_style_example  # noqa: E402


def main() -> int:
    failures = []

    # 1. Section blueprint sanity.
    keys = [s[0] for s in _SECTION_SPECS]
    if len(keys) != 13:
        failures.append(f"expected 13 sections, got {len(keys)}")
    if len(set(keys)) != len(keys):
        failures.append(f"duplicate section keys: {keys}")

    # 2. Banned-word detector.
    hits = _banned_hits("The team sought to leverage synergy and build a robust, seamless rollout.")
    if not ({"leverage", "synergy", "robust", "seamless"} <= set(hits)):
        failures.append(f"banned detector missed words: {hits}")
    if _banned_hits("The plant reduced defects by 40 percent over two years."):
        failures.append("banned detector false-positive on clean prose")
    if not BANNED_WORDS:
        failures.append("BANNED_WORDS empty")

    # 3. Draft assembly.
    draft = CaseStudyDraft(
        company="ACME", title="ACME: A Case",
        sections=[Section(key="a", title="One", body="word " * 50),
                  Section(key="b", title="Two", body="word " * 30)],
    )
    if draft.word_count != 80:
        failures.append(f"word_count wrong: {draft.word_count}")
    if "## One" not in draft.full_text() or "# ACME: A Case" not in draft.full_text():
        failures.append("full_text missing headings")

    # 4. Reference style index (local embeddings; no key).
    try:
        idx = build_reference_index()
        count = idx.collection.count()
        if count <= 0:
            failures.append("reference index empty after build")
        else:
            example = get_style_example(idx, "company background protagonist decision")
            if not example.strip():
                failures.append("get_style_example returned empty")
            else:
                print(f"  reference index: {count} chunks; sample style len={len(example)}")
    except Exception as exc:
        failures.append(f"reference index build raised: {exc}")

    if failures:
        print("[STAGE 5 SMOKE] [FAIL]")
        for f in failures:
            print("  -", f)
        return 1
    print("[STAGE 5 SMOKE] [PASS] generator blueprint + style index OK (live generation deferred: no key).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
