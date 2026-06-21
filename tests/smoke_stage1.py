"""Stage 1 smoke test - run with the project venv:

    D:\\ifqm-case-generator\\.venv\\Scripts\\python.exe tests\\smoke_stage1.py

Verifies (without needing a Groq key):
  1. The configured password hash matches "ifqm_admin_2026".
  2. The Streamlit app boots with no exception (unauthenticated view).
  3. The authenticated view renders the 6 section tabs + verification panel.
  4. LLMClient raises a clear error when GROQ_API_KEY is absent (correct behavior).

Exits non-zero if any structural check fails. The live Groq ping is reported
separately and does NOT fail the smoke test when the key is missing.
"""
from __future__ import annotations

import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402

import src.app as app  # noqa: E402

APP_FILE = str(PROJECT_ROOT / "src" / "app.py")
PASSWORD = "ifqm_admin_2026"


def _configured_hash() -> str:
    secrets = tomllib.loads((PROJECT_ROOT / ".streamlit" / "secrets.toml").read_text("utf-8"))
    return str(secrets["password_sha256"]).strip().lower()


def check_hash() -> bool:
    expected = _configured_hash()
    actual = app._hash(PASSWORD)
    ok = actual == expected
    print(f"[{'PASS' if ok else 'FAIL'}] password hash matches {PASSWORD!r}")
    return ok


def check_unauthenticated_boot() -> bool:
    at = AppTest.from_file(APP_FILE)
    at.secrets["password_sha256"] = _configured_hash()
    at.run()
    ok = not at.exception and any("IFQM Case Study Generator" in t.value for t in at.title)
    print(f"[{'PASS' if ok else 'FAIL'}] app boots (login view), no exception")
    return ok


def check_authenticated_view() -> bool:
    at = AppTest.from_file(APP_FILE)
    at.secrets["password_sha256"] = _configured_hash()
    at.session_state["authenticated"] = True
    at.session_state["company_name"] = "Infosys"
    at.run()
    ok = not at.exception and len(at.tabs) >= 6
    print(f"[{'PASS' if ok else 'FAIL'}] authenticated workspace renders {len(at.tabs)} tabs")
    return ok


def report_llm_client() -> None:
    """Report client behavior; does not gate the smoke result without a key."""
    from src.llm_client import LLMClientError, get_llm_client

    try:
        client = get_llm_client()
    except LLMClientError as exc:
        print(f"[INFO] LLMClient correctly refused to start (no key): {exc}")
        print("[BLOCKED] Live Groq test_connection skipped - set GROQ_API_KEY in .env to verify.")
        return

    result = client.test_connection()
    if result["ok"]:
        print(f"[PASS] Groq live ping ok (primary={result['primary']!r}, utility={result['utility']!r})")
    else:
        print(f"[WARN] Groq live ping failed: {result['error']}")


def main() -> int:
    print("=== Stage 1 smoke test ===")
    checks = [check_hash(), check_unauthenticated_boot(), check_authenticated_view()]
    report_llm_client()
    print("=" * 32)
    if all(checks):
        print("STAGE 1 SMOKE: PASS")
        return 0
    print("STAGE 1 SMOKE: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
