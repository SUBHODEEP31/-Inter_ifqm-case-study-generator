# IFQM Multi-Agent Case Study Generator

Autonomous pipeline that turns an Indian company name (+ optional corporate PDFs) into a
publication-grade, fact-verified business case study. Groq-only inference, local
embeddings/rerank/NLI, Streamlit UI. Runs entirely on consumer hardware.

## Requirements
- **Python 3.11** (mandatory). `torch`/`docling` have no wheels for 3.12+/3.14.
- Windows: **GTK3 runtime** for WeasyPrint PDF export
  ([installer](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases)).
- **Node.js** (present) for optional `@mermaid-js/mermaid-cli` diagram rendering.
- A free **Groq API key** from <https://console.groq.com>.

## Setup (Windows / PowerShell)
```powershell
cd D:\ifqm-case-generator
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
crawl4ai-setup                 # installs the Playwright browser for Crawl4AI
copy .env.example .env         # then paste your GROQ_API_KEY into .env
python setup_check.py          # pre-flight: Python / key / GTK3
```

## Run
```powershell
.\.venv\Scripts\Activate.ps1
streamlit run src\app.py
```
Default login password: `ifqm_admin_2026` (stored as a SHA-256 hash in
`.streamlit/secrets.toml`; rotate via the snippet in that file).

## Pipeline stages
0. Foundation 1. Streamlit shell + LLM client 2. Ingestion (Docling + ddgs + Crawl4AI)
3. Hybrid retrieval (ChromaDB + BM25 + RRF + bge-reranker) 4. Pydantic case brief
5. Style-transferred generation 6. CoV + MiniCheck verification 7. Human review gate
8. Export (Word + WeasyPrint PDF + Mermaid).

## Models
- Generation: `llama-3.3-70b-versatile` (Groq) · Utility: `llama-3.1-8b-instant` (Groq)
- Embeddings: `BAAI/bge-large-en-v1.5` · Rerank: `BAAI/bge-reranker-v2-m3`
- NLI fact-check: `lytang/MiniCheck-DeBERTa-v3-Large`

## Deferred to v2
ColPali visual indexing, LightRAG/Neo4j graph reasoning, Langfuse observability,
DeepEval, RAGAS, Ollama failover, SearXNG.
