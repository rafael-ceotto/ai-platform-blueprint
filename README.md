# Konsole.ai

> A local-first RAG platform: FastAPI + Ollama + FAISS, with hybrid
> retrieval, streaming answers, and full observability — no API keys,
> no billing, nothing leaves your machine.

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-blue?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 🚀 Try It

**🖱️ Just want to click around?** (need [Docker Desktop](https://www.docker.com/products/docker-desktop/))

```bash
git clone <this-repo-url> && cd konsole-ai
cp .env.example .env
docker compose up -d --build

# First run only — pulls the two local models (~5GB total)
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text
```

Open **http://localhost:8501** — upload a document, search it, ask it a
question, and watch the answer stream in with cited sources.

**💻 Prefer the API?**

- Swagger UI: **http://localhost:8000/docs**
- Or:
  ```bash
  curl -X POST http://localhost:8000/api/v1/documents/ask \
    -H "Content-Type: application/json" -H "X-API-Key: dev-local-key" \
    -d '{"query": "What does this API do?"}'
  ```

**Want the observability stack too** (distributed tracing, metrics,
dashboards)? It's opt-in, so the default stack stays lean:

```bash
TRACING_ENABLED=true METRICS_ENABLED=true docker compose --profile observability up -d --build
```

Then: Jaeger at http://localhost:16686, Prometheus at
http://localhost:9090, Grafana (with a provisioned dashboard) at
http://localhost:3000.

No Docker? `make run` (API) and `make ui` (demo UI) work with a local
Python install too.

## What it does

- Ingests text or files (PDF, Markdown, TXT, HTML), chunks and embeds
  them, and stores them in a FAISS index.
- Answers questions with **hybrid retrieval** (vector + keyword search)
  and **query routing** — greetings skip retrieval entirely, real
  questions get re-ranked context before the local model answers.
- **Streams** the answer token-by-token, with cited sources, in
  whatever language you asked in.
- Everything's behind API-key auth and per-key rate limiting.
- A minimal Streamlit UI covers all of this beyond Swagger.
- Also runs as an **MCP server** (`mcp_server/`, stdio) — `ask`/`search`/
  `ingest_text` as tools any MCP client (e.g. Claude Desktop) can call,
  zero hosting cost (see ADR-0016).

## Tech Stack

FastAPI · Ollama · FAISS · LangChain / LangGraph · Streamlit · MCP ·
OpenTelemetry + Prometheus + Grafana · Docker Compose · pytest / ruff / mypy

Every non-obvious choice — why FAISS over Qdrant, why local Ollama over
a hosted API, why hybrid retrieval, why the UI ships as its own image —
is written up in [`docs/adr/`](docs/adr/), one ADR per decision. A full
C4 architecture breakdown lives in
[`docs/architecture/c4-model.md`](docs/architecture/c4-model.md).

## API Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe |
| `GET` | `/api/v1/health/ready` | Readiness probe (checks Ollama) |
| `POST` | `/api/v1/documents` * | Ingest raw text |
| `POST` | `/api/v1/documents/upload` * | Ingest a PDF/Markdown/TXT/HTML file |
| `POST` | `/api/v1/documents/search` * | Hybrid search |
| `POST` | `/api/v1/documents/ask` * | Ask a question; `"stream": true` for SSE |
| `GET` | `/docs` | Swagger UI |

\* Requires an `X-API-Key` header, rate-limited per key.

## Configuration

Everything's environment-driven — see [`.env.example`](.env.example)
for the full list. The one you'll actually want to change before any
real deployment: `API_KEYS` (defaults to `["dev-local-key"]`).

## Development

```bash
make install     # install package + dev dependencies
make test         # run the test suite with coverage
make check        # lint + typecheck + test (what CI runs)
```

CI run notifications (pass/fail) can be sent to Slack via GitHub's own
Slack app -- no code involved: `/github subscribe <owner>/<repo>
workflows:{event:"push" branch:"main"}` in any channel. See
[GitHub's Slack integration docs](https://docs.github.com/en/integrations/how-tos/slack/customize-notifications).

## License

[MIT](LICENSE)
