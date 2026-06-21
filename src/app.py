"""Streamlit front-end for the IFQM Case Study Generator.

Stage 1 scope: corporate-themed shell, SHA-256 password gate, dual-panel
workspace (left = generated sections in tabs, right = verification table), and a
live Groq connection check. Later stages wire ingestion, generation, review, and
export into these panels.

Run from the project root:
    streamlit run src\\app.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import streamlit as st

# Ensure the project root is importable when launched via `streamlit run src/app.py`
# (Streamlit puts src/ on sys.path, not the project root).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.logger import get_logger  # noqa: E402

log = get_logger("app")

SECTION_TABS = (
    "Background",
    "The Dilemma",
    "Intervention",
    "Results",
    "Learning Takeaways",
    "Exhibits",
)

CUSTOM_CSS = """
<style>
  .main .block-container { padding-top: 2rem; max-width: 100%; }
  h1, h2, h3 { color: #0F172A; font-family: 'Helvetica Neue', Arial, sans-serif; }
  section[data-testid="stSidebar"] { background-color: #1E293B; }
  section[data-testid="stSidebar"] * { color: #E2E8F0; }
  .ifqm-brand { font-size: 1.15rem; font-weight: 700; color: #FFFFFF; letter-spacing: .04em; }
  .ifqm-panel-title {
    color: #0F172A; font-weight: 700; border-bottom: 2px solid #2563EB;
    padding-bottom: .35rem; margin-bottom: .75rem;
  }
  .ifqm-empty { color: #64748B; font-style: italic; }
</style>
"""


def _hash(text: str) -> str:
    """Return the SHA-256 hex digest of `text`."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expected_hash() -> str | None:
    """Read the configured password hash from secrets.toml."""
    try:
        return str(st.secrets["password_sha256"]).strip().lower()
    except Exception:
        return None


UPLOAD_DIR = _PROJECT_ROOT / "data" / "uploads"


def _init_state() -> None:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("company_name", "")
    st.session_state.setdefault("sections", {})          # section -> generated text
    st.session_state.setdefault("verification_rows", []) # list of citation/verdict dicts
    st.session_state.setdefault("ingestion", None)       # IngestionResult-like summary


def render_login() -> None:
    """Render the password gate. Sets session_state.authenticated on success."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("IFQM Case Study Generator")
    st.caption("Restricted access. Enter the project password to continue.")

    expected = _expected_hash()
    with st.form("login_form", clear_on_submit=False):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if not submitted:
        return

    if expected is None:
        st.error(
            "No password hash configured. Set `password_sha256` in "
            "`.streamlit/secrets.toml`."
        )
        return

    if _hash(password) == expected:
        st.session_state.authenticated = True
        log.info("Login success.")
        st.rerun()
    else:
        log.warning("Login failed: incorrect password.")
        st.error("Incorrect password.")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="ifqm-brand">IFQM &middot; CASE ENGINE</div>', unsafe_allow_html=True)
        st.divider()

        st.session_state.company_name = st.text_input(
            "Target company", value=st.session_state.company_name, placeholder="e.g. Infosys"
        )
        uploaded = st.file_uploader(
            "Supporting documents (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            help="Optional. Parsed with Docling during ingestion.",
        )

        run_disabled = not st.session_state.company_name.strip()
        if st.button("Run ingestion", use_container_width=True, disabled=run_disabled):
            _run_ingestion(uploaded)

        st.divider()
        if st.button("Test Groq connection", use_container_width=True):
            _run_connection_test()

        st.divider()
        if st.button("Log out", use_container_width=True):
            st.session_state.authenticated = False
            st.rerun()


def _run_connection_test() -> None:
    """Build the LLM client and ping both Groq models, reporting status inline."""
    try:
        from src.llm_client import get_llm_client

        client = get_llm_client()
    except Exception as exc:
        st.sidebar.error(f"Client init failed: {exc}")
        log.error(f"Connection test client init failed: {exc}")
        return

    with st.spinner("Pinging Groq (primary + utility)..."):
        result = client.test_connection()

    if result["ok"]:
        st.sidebar.success(
            f"Groq OK\nprimary={result['primary']!r}\nutility={result['utility']!r}"
        )
    else:
        st.sidebar.error(f"Groq FAILED: {result['error']}")


def _run_ingestion(uploaded_files) -> None:
    """Persist uploaded PDFs, run Stage 2 ingestion, and populate the panels."""
    from src.ingestion import ingest

    company = st.session_state.company_name.strip()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    pdf_paths: list[str] = []
    for uf in uploaded_files or []:
        dest = UPLOAD_DIR / uf.name
        dest.write_bytes(uf.getbuffer())
        pdf_paths.append(str(dest))

    with st.spinner(f"Ingesting sources for {company}... (Docling + web crawl)"):
        try:
            result = ingest(company, pdf_paths=pdf_paths)
        except Exception as exc:
            st.sidebar.error(f"Ingestion failed: {type(exc).__name__}: {exc}")
            log.error(f"Ingestion failed for {company!r}: {exc}")
            return

    st.session_state.ingestion = {
        "company": result.company,
        "pdf_count": len(result.pdf_docs),
        "web_count": len(result.web_docs),
    }
    # Surface the source inventory in the right-hand panel.
    st.session_state.verification_rows = [
        {
            "source_id": d.source_id,
            "type": d.source_type.value,
            "title": (d.title[:60] + "...") if len(d.title) > 60 else d.title,
            "origin": d.origin,
            "chars": d.char_count,
        }
        for d in result.docs
    ]
    # Preview the first parsed document in the Background tab.
    if result.docs:
        preview = result.docs[0].text[:4000]
        st.session_state.sections["Background"] = (
            f"**Ingestion preview - {result.docs[0].source_id}** "
            f"({result.docs[0].source_type.value})\n\n{preview}"
        )
    st.sidebar.success(
        f"Ingested {len(result.pdf_docs)} PDF + {len(result.web_docs)} web sources."
    )


def render_workspace() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    company = st.session_state.company_name or "(no company selected)"
    st.title("Case Study Workspace")
    st.caption(f"Target: {company}")

    left, right = st.columns([2, 1], gap="large")

    with left:
        st.markdown('<div class="ifqm-panel-title">Generated Case Study</div>', unsafe_allow_html=True)
        tabs = st.tabs(list(SECTION_TABS))
        for tab, name in zip(tabs, SECTION_TABS):
            with tab:
                content = st.session_state.sections.get(name)
                if content:
                    st.markdown(content)
                else:
                    st.markdown(
                        f'<p class="ifqm-empty">No content yet for "{name}". '
                        "Run the pipeline (Stages 2-6) to populate this section.</p>",
                        unsafe_allow_html=True,
                    )

    with right:
        st.markdown('<div class="ifqm-panel-title">Verification &amp; Sources</div>', unsafe_allow_html=True)
        rows = st.session_state.verification_rows
        if rows:
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.markdown(
                '<p class="ifqm-empty">Verification data appears here once claims are '
                "extracted and fact-checked (Stage 6). Each row links a claim to its "
                "source document, page, and verdict.</p>",
                unsafe_allow_html=True,
            )


def main() -> None:
    st.set_page_config(page_title="IFQM Case Study Generator", page_icon="📘", layout="wide")
    _init_state()
    if st.session_state.authenticated:
        render_sidebar()
        render_workspace()
    else:
        render_login()


if __name__ == "__main__":
    main()
