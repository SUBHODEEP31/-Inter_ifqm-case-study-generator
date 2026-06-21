"""Pre-flight environment validator for the IFQM Case Study Generator.

Run with the project venv BEFORE first launch:
    D:\\ifqm-case-generator\\.venv\\Scripts\\python.exe setup_check.py

Checks:
  1. Python is 3.11.x (torch/docling lack wheels for 3.12+/3.14).
  2. GROQ_API_KEY is present in .env.
  3. GTK3 runtime is loadable (required by WeasyPrint on Windows).

Exits non-zero on a hard failure so it can gate CI / launch scripts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
GTK_DOWNLOAD_URL = (
    "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases"
)


def _ok(msg: str) -> None:
    print(f"[ OK ] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_python() -> bool:
    """Verify the interpreter is CPython 3.11.x."""
    major, minor = sys.version_info[:2]
    if (major, minor) == (3, 11):
        _ok(f"Python {sys.version.split()[0]}")
        return True
    _fail(
        f"Python {major}.{minor} detected; this project requires 3.11.x. "
        f"Recreate the venv with: py -3.11 -m venv {PROJECT_ROOT / '.venv'}"
    )
    return False


def check_groq_key() -> bool:
    """Verify GROQ_API_KEY is set (loaded from .env if python-dotenv is available)."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        _warn("python-dotenv not installed yet; reading os.environ only.")

    key = os.getenv("GROQ_API_KEY", "").strip()
    if key:
        _ok("GROQ_API_KEY is set.")
        return True
    _fail(
        "GROQ_API_KEY is empty. Add it to D:\\ifqm-case-generator\\.env "
        "(get one free at https://console.groq.com)."
    )
    return False


def check_gtk3() -> bool:
    """Verify the GTK3 runtime can be loaded by WeasyPrint on Windows."""
    if os.name != "nt":
        _ok("Non-Windows OS; skipping GTK3 check.")
        return True
    try:
        import weasyprint  # noqa: F401  (import triggers native lib loading)

        _ok("WeasyPrint imported; GTK3 runtime is loadable.")
        return True
    except ImportError:
        _warn("WeasyPrint not installed yet; GTK3 check deferred until export stage.")
        return True
    except OSError as exc:
        _fail(
            "WeasyPrint could not load the GTK3 runtime "
            f"({exc}). Install GTK3 for Windows from:\n       {GTK_DOWNLOAD_URL}"
        )
        return False


def main() -> int:
    print("=== IFQM Case Study Generator :: pre-flight ===")
    results = {
        "python": check_python(),
        "groq_key": check_groq_key(),
        "gtk3": check_gtk3(),
    }
    print("=" * 48)
    hard_failures = [name for name, ok in results.items() if not ok]
    if hard_failures:
        print(f"PRE-FLIGHT FAILED: {', '.join(hard_failures)}")
        return 1
    print("PRE-FLIGHT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
