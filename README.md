# Konsole.ai

> A production-grade starting point for building AI/LLM platforms: FastAPI
> service, local-first LLM runtime (Ollama), and a vector-search layer
> (FAISS), designed to scale from prototype to production.

[![CI](https://img.shields.io/badge/CI-GitHub_Actions-blue?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 🚀 Try It

No API keys, no billing, no sign-up — everything runs on your machine.

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
question, and watch the answer stream in with cited sources. No terminal
needed after this.

**💻 Technical reviewer, want the API directly?**

- Swagger UI, try every endpoint interactively: **http://localhost:8000/docs**
- Or from a terminal, after the setup above:
  ```bash
  curl -X POST http://localhost:8000/api/v1/documents/ask \
    -H "Content-Type: application/json" -H "X-API-Key: dev-local-key" \
    -d '{"query": "What does this API do?"}'
  ```
- Full endpoint-by-endpoint walkthrough (upload, hybrid search, SSE
  streaming) and the observability stack (Jaeger/Prometheus/Grafana):
  see [Quickstart](#quickstart) below.

## Overview

Konsole.ai is a reference architecture — not a toy demo — for
teams building products on top of LLMs. It ships with the plumbing most AI
products need on day one:

- A **FastAPI** service with structured logging, typed settings, liveness
  and readiness probes, and a clean layer boundary between API, services,
  and core config.
- A **local-first LLM runtime** via [Ollama](https://ollama.com/), so the
  whole stack runs with `docker compose up` — no API keys, no billing, no
  data leaving your machine (see [ADR-0002](docs/adr/0002-llm-runtime-ollama-vs-external-apis.md)).
- A **vector search** layer built on FAISS for retrieval-augmented
  generation, behind an internal abstraction so the backend can evolve
  without rewriting call sites (see [ADR-0001](docs/adr/0001-vector-store-faiss-vs-qdrant.md)).
- **Retrieval-augmented generation**, not just retrieval: the local SLM
  synthesizes answers from retrieved context via a LangChain LCEL chain
  (see [ADR-0004](docs/adr/0004-langchain-for-answer-generation.md)).
- **Centralized error handling**: unhandled exceptions never leak internal
  details to callers — always a safe, logged, JSON `500` response, not
  Starlette's default plain-text page.
- **Hybrid retrieval + query routing**: semantic (vector) and keyword
  (BM25) search fused via Reciprocal Rank Fusion, and a LangGraph query
  router that skips retrieval entirely for greetings/meta questions
  (see [ADR-0006](docs/adr/0006-hybrid-retrieval-and-query-routing.md)).
- **Streaming answers**: `POST /documents/ask` can stream the generated
  answer token-by-token over Server-Sent Events instead of waiting for
  the full response (see [ADR-0007](docs/adr/0007-sse-streaming.md)).
- **Observability**: OpenTelemetry distributed tracing (FastAPI + the
  outgoing calls to Ollama) exported to Jaeger, Prometheus metrics, and
  a provisioned Grafana dashboard — all live with `docker compose up`
  (see [ADR-0008](docs/adr/0008-observability-tracing-metrics-dashboards.md)).
- **A minimal demo UI** (Streamlit): ask questions with streamed
  answers and cited sources, run hybrid search, and ingest documents —
  all beyond Swagger, zero-config against the default stack
  (see [ADR-0010](docs/adr/0010-streamlit-demo-ui.md)).
- **Architecture decision records (ADRs)** documenting the *why* behind
  every non-obvious choice, and a **C4 model** describing the system at
  three levels of zoom.

**Sprint 1 — Project Foundation** laid the base: FastAPI app, health
probes, config, logging. **Sprint 2 — RAG Pipeline** built the first
end-to-end retrieval loop on top of it: document ingestion, chunking,
embedding, and a `VectorStore` port with a FAISS adapter behind it.
**Sprint 3 — Access Control** added API-key auth and per-key rate
limiting in front of that pipeline. **Sprint 4 — Answer Generation**
closed the loop: `POST /documents/ask` has the local SLM actually
generate an answer from retrieved context (via a LangChain LCEL chain),
instead of only returning raw chunks. **Sprint 5 — Document Loaders** added `POST /documents/upload` for PDF,
Markdown, TXT, and HTML files, not just raw JSON text, and closed out
the last piece of Sprint 3's scope — centralized error handling so
unhandled exceptions return a safe, logged JSON response instead of
leaking internals. **Sprint 6 — Hybrid Retrieval & Query Routing**
combines semantic and keyword search via RRF, adds a
LangGraph router that skips retrieval for queries that don't need it,
and re-ranks retrieved candidates via the local SLM before generating
an answer. **Sprint 7 — Streaming** added token-by-token SSE streaming
to `/documents/ask`, reusing the same query graph. **Sprint 8 —
Observability** added distributed tracing (OpenTelemetry -> Jaeger),
metrics (Prometheus), and a provisioned Grafana dashboard. **Sprint 9 —
Demo UI** (this repo), the last planned step, added a minimal Streamlit
UI showing off everything above beyond Swagger.

## Architecture

```mermaid
C4Container
    title Container Diagram — Konsole.ai

    Person(user, "End User")

    System_Boundary(platform, "Konsole.ai") {
        Container(api, "API Service", "FastAPI / Python 3.12", "REST endpoints, orchestration, validation")
        Container(vectorstore, "Vector Store", "FAISS (in-process)", "Embedding storage + similarity search")
        ContainerDb(datavol, "Data Volume", "Docker volume", "Persists index files")
    }

    Container_Ext(ollama, "Ollama", "Container", "Local LLM inference")

    Rel(user, api, "HTTPS", "JSON/REST")
    Rel(api, vectorstore, "search / upsert", "in-process")
    Rel(vectorstore, datavol, "read/write", "filesystem")
    Rel(api, ollama, "generate / embed", "HTTP :11434")
```

Full C4 breakdown (Context → Container → Component): [`docs/architecture/c4-model.md`](docs/architecture/c4-model.md).

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| API framework | FastAPI + Uvicorn | Async-native, typed, auto-generated OpenAPI docs |
| Config | Pydantic Settings | Typed, validated, env/`.env`-driven configuration |
| LLM runtime | Ollama | Local-first, zero-cost iteration ([ADR-0002](docs/adr/0002-llm-runtime-ollama-vs-external-apis.md)) |
| Vector store | FAISS | In-process, no extra infra for MVP scale ([ADR-0001](docs/adr/0001-vector-store-faiss-vs-qdrant.md)) |
| Answer generation | LangChain (`langchain-core` + `langchain-ollama`) | LCEL retriever/prompt/LLM chain over the local SLM ([ADR-0004](docs/adr/0004-langchain-for-answer-generation.md)) |
| Document loaders | `pypdf` + `beautifulsoup4` | Lightweight PDF/HTML text extraction, no heavy `unstructured` dependency ([ADR-0005](docs/adr/0005-document-loaders.md)) |
| Hybrid retrieval | `rank-bm25` + `langchain_classic`'s `EnsembleRetriever` | BM25 + vector search fused via RRF; not `langchain_community` (archived) ([ADR-0006](docs/adr/0006-hybrid-retrieval-and-query-routing.md)) |
| Query routing | LangGraph | Routes each `/ask` query to a direct answer or the full retrieve/rerank/generate path ([ADR-0006](docs/adr/0006-hybrid-retrieval-and-query-routing.md)) |
| Streaming | Server-Sent Events (FastAPI `StreamingResponse`) | Token-by-token `/ask` responses, no new dependency ([ADR-0007](docs/adr/0007-sse-streaming.md)) |
| Tracing | OpenTelemetry -> Jaeger v2 | FastAPI + httpx auto-instrumentation, OTLP export, log/trace correlation ([ADR-0008](docs/adr/0008-observability-tracing-metrics-dashboards.md)) |
| Metrics & dashboards | `prometheus-fastapi-instrumentator` + Prometheus + Grafana | Default RED metrics, provisioned dashboard, zero click-ops setup ([ADR-0008](docs/adr/0008-observability-tracing-metrics-dashboards.md)) |
| Demo UI | Streamlit + `httpx2` | Thin client over the API; `httpx2`'s native SSE support consumes `/ask` streaming directly ([ADR-0010](docs/adr/0010-streamlit-demo-ui.md)) |
| Packaging | `pyproject.toml` (Hatchling) | Standard, PEP 621-compliant |
| Lint / format | Ruff | Single fast tool for both |
| Type checking | mypy (strict) | Catch contract errors before runtime |
| Tests | pytest + httpx TestClient | Fast, no running server required |
| Containerization | Docker (multi-stage) + Compose | Reproducible local + deploy story |
| CI | GitHub Actions | Lint, type-check, test, build on every PR |

## Project Structure

```
konsole-ai/
├── backend/                  # HTTP surface + orchestration
│   ├── main.py                 # FastAPI app factory + lifespan
│   ├── config/                  # Typed settings (env-driven)
│   ├── api/                     # Versioned HTTP interface
│   │   ├── deps.py                # Shared dependency providers
│   │   ├── security.py            # API key verification
│   │   ├── rate_limit.py          # In-memory per-key rate limiter
│   │   └── v1/                    # router.py, endpoints/ (health.py, documents.py)
│   ├── models/                  # Pydantic request/response models
│   └── services/                 # Orchestration (IngestionService, GenerationService)
├── ingestion/                 # Document ingestion mechanics
│   ├── chunking/                # Text chunking
│   └── loaders/                 # PDF / HTML / TXT / Markdown text extraction
├── retrieval/                 # Vector search + retrieval
│   ├── vector_store/            # VectorStore port + FAISS adapter
│   └── retriever/               # Vector/BM25/hybrid LangChain retrievers
├── llm/                       # Model runtime clients + orchestration
│   ├── ollama/                  # Ollama HTTP client (generate + embed)
│   ├── prompts/                  # RAG / classify / rerank prompt templates
│   └── routing/                  # LangGraph query-routing graph
├── observability/             # Cross-cutting operational concerns
│   ├── logging/                 # Structured JSON logging (+ trace/span correlation)
│   ├── tracing/                  # OpenTelemetry setup (FastAPI + httpx -> Jaeger)
│   └── metrics/                  # Prometheus instrumentation (/metrics)
├── infra/                     # Local observability infra config
│   ├── prometheus/               # Scrape config
│   └── grafana/                  # Provisioned datasource + dashboard
├── ui/                        # Streamlit demo UI (separate deployable)
│   ├── app.py                   # Sidebar + Ask/Search/Ingest tabs
│   ├── api_client.py             # All HTTP calls against the API (httpx2)
│   ├── requirements.txt          # streamlit, httpx2 -- own deps, own image
│   └── Dockerfile
├── tests/                     # pytest suite
├── docs/
│   ├── adr/                    # Architecture Decision Records
│   └── architecture/           # C4 model diagrams (Mermaid)
├── .github/workflows/ci.yml   # Lint + typecheck + test + build
├── Dockerfile                  # Multi-stage, non-root, healthchecked
├── docker-compose.yml          # api + ollama + jaeger + prometheus + grafana + ui
├── pyproject.toml              # Deps, tooling config
└── Makefile                    # Common dev commands
```

## Quickstart

### Option A — Docker (recommended)

Runs the API and Ollama together; no local Python setup needed.

```bash
git clone <this-repo-url>
cd konsole-ai
cp .env.example .env

docker compose up -d --build

# Pull the generation and embedding models into the running Ollama
# container (first run only). The embedding model is required for the
# /documents endpoints — skipping it returns a 500 (Ollama 404s the
# embeddings call for a model it doesn't have).
docker compose exec ollama ollama pull llama3.1:8b
docker compose exec ollama ollama pull nomic-embed-text

curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/ready

# Try the RAG pipeline (POST /documents* requires the X-API-Key header;
# "dev-local-key" is the default in .env.example — change it before any
# real deployment)
curl -X POST http://localhost:8000/api/v1/documents \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"text": "FastAPI is a modern Python web framework.", "metadata": {"source": "readme"}}'

curl -X POST http://localhost:8000/api/v1/documents/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"query": "What web framework is used?"}'

# Or have the SLM generate an answer instead of raw chunks
curl -X POST http://localhost:8000/api/v1/documents/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"query": "What web framework is used?"}'

# Or upload a file directly (PDF, Markdown, TXT, or HTML)
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-API-Key: dev-local-key" \
  -F "file=@/path/to/your/document.pdf" \
  -F 'metadata={"source": "upload"}'

# A greeting skips retrieval entirely (LangGraph query routing)
curl -X POST http://localhost:8000/api/v1/documents/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"query": "hi, what can you help me with?"}'

# Or stream the answer token-by-token via Server-Sent Events (-N disables
# curl's output buffering so tokens print as they arrive)
curl -N -X POST http://localhost:8000/api/v1/documents/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-local-key" \
  -d '{"query": "What web framework is used?", "stream": true}'
```

API docs (Swagger UI): http://localhost:8000/docs

**Demo UI** (beyond Swagger): http://localhost:8501 — ask questions
with streamed answers and cited sources, run hybrid search, and ingest
documents, all zero-config against the default stack.

Observability, all live automatically alongside the API:

| UI | URL | What you'll see |
|---|---|---|
| Jaeger | http://localhost:16686 | Traces spanning each request and its calls to Ollama, after you've hit a few endpoints |
| Prometheus | http://localhost:9090/targets | The `api` scrape target reporting `UP` |
| Grafana | http://localhost:3000 | A provisioned "Konsole.ai - API Overview" dashboard (anonymous viewer access, no login needed) |

### Option B — Local Python

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
cp .env.example .env

# Run Ollama separately (native install or `docker run -p 11434:11434 ollama/ollama`)
make run   # or: uvicorn backend.main:app --reload

# In a separate shell, the demo UI (talks to the API over HTTP only,
# its own dependencies -- see ui/requirements.txt)
make ui    # or: cd ui && pip install -r requirements.txt && streamlit run app.py
```

## Configuration

All configuration is environment-driven (`backend/config/settings.py`); see
[`.env.example`](.env.example) for the full list. Key variables:

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `local` | `local` \| `development` \| `staging` \| `production` |
| `LOG_JSON` | `true` | Structured JSON logs vs. human-readable |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama daemon endpoint |
| `OLLAMA_MODEL` | `llama3.1:8b` | Default model for generation |
| `VECTOR_STORE_PATH` | `./data/vector_store` | FAISS index location |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Ollama model used to embed chunks and queries |
| `CHUNK_SIZE` | `500` | Max characters per chunk during ingestion |
| `CHUNK_OVERLAP` | `50` | Character overlap between adjacent chunks |
| `SEARCH_TOP_K_DEFAULT` | `5` | Default number of results returned by search |
| `API_KEYS` | `["dev-local-key"]` | Valid `X-API-Key` values for `/documents*`. Empty list fails closed. **Change before deploying.** |
| `RATE_LIMIT_REQUESTS` | `60` | Max requests per key per window on `/documents*` |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate limit window length, in seconds |
| `MAX_UPLOAD_SIZE_BYTES` | `10000000` | Max accepted file size for `/documents/upload` (10 MB) |
| `RERANK_TOP_N` | `3` | How many hybrid-retrieved candidates survive LLM re-ranking into `/ask`'s generation context |
| `TRACING_ENABLED` | `false` | OpenTelemetry tracing on/off. `docker-compose.yml` sets this `true` for the live stack; off by default (incl. tests) — see [ADR-0008](docs/adr/0008-observability-tracing-metrics-dashboards.md) |
| `METRICS_ENABLED` | `false` | Prometheus `/metrics` endpoint on/off. Same on/off pattern as `TRACING_ENABLED` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | Where traces are exported (OTLP/gRPC); `http://jaeger:4317` in Docker |

## Development

```bash
make install     # install package + dev dependencies
make run          # run the API with hot reload
make test         # run the test suite with coverage
make lint         # ruff check
make format       # ruff format + autofix
make typecheck    # mypy --strict
make check        # lint + typecheck + test (what CI runs)
```

## API Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe — process is up |
| `GET` | `/api/v1/health/ready` | Readiness probe — verifies Ollama connectivity |
| `POST` | `/api/v1/documents` * | Ingest a document: chunk, embed, and store it |
| `POST` | `/api/v1/documents/upload` * | Ingest an uploaded PDF, Markdown, TXT, or HTML file |
| `POST` | `/api/v1/documents/search` * | Hybrid (vector + BM25) search, return the nearest chunks |
| `POST` | `/api/v1/documents/ask` * | Route, retrieve (hybrid), re-rank, and have the local SLM generate an answer. Set `"stream": true` for token-by-token Server-Sent Events instead of a single JSON response |
| `GET` | `/docs` | Interactive OpenAPI (Swagger) docs |
| `GET` | `/redoc` | ReDoc API reference |

\* Requires an `X-API-Key` header (see [ADR-0003](docs/adr/0003-api-key-auth-and-rate-limiting.md)) and is subject to per-key rate limiting.

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [0001](docs/adr/0001-vector-store-faiss-vs-qdrant.md) | Vector store: FAISS (in-process) over Qdrant, for now |
| [0002](docs/adr/0002-llm-runtime-ollama-vs-external-apis.md) | LLM runtime: Ollama (local-first) over external APIs, for now |
| [0003](docs/adr/0003-api-key-auth-and-rate-limiting.md) | Access control: API keys over OAuth2; in-memory rate limiting over Redis, for now |
| [0004](docs/adr/0004-langchain-for-answer-generation.md) | Answer generation: LangChain LCEL chain (`langchain-core` + `langchain-ollama`) over hand-rolled prompt assembly |
| [0005](docs/adr/0005-document-loaders.md) | Document loaders: `pypdf` + `beautifulsoup4` over `langchain-community`'s `unstructured`-based loaders |
| [0006](docs/adr/0006-hybrid-retrieval-and-query-routing.md) | Hybrid retrieval (hand-rolled BM25 + `langchain_classic`'s `EnsembleRetriever`), LangGraph query routing, SLM-based re-ranking |
| [0007](docs/adr/0007-sse-streaming.md) | Streaming answers: Server-Sent Events over WebSocket, `stream` request field over a separate endpoint, same query graph reused via `.astream()` |
| [0008](docs/adr/0008-observability-tracing-metrics-dashboards.md) | Observability: OpenTelemetry (FastAPI + httpx) exported to Jaeger v2 over OTLP; `prometheus-fastapi-instrumentator` + Prometheus + a provisioned Grafana dashboard |
| [0009](docs/adr/0009-async-ingestion-message-broker.md) | Async ingestion / message broker (Kafka or similar): not needed yet — ingestion stays synchronous until a concrete decoupling/fan-out need exists |
| [0010](docs/adr/0010-streamlit-demo-ui.md) | Demo UI: Streamlit as a separate deployable (own deps/image) over reusing the API's environment; `httpx2` for native SSE consumption |

New ADRs follow [`docs/adr/template.md`](docs/adr/template.md).

## Roadmap

Sprint 1 established the foundation, Sprint 2 added the RAG pipeline,
Sprint 3 added access control, Sprint 4 closed the retrieval-augmented
*generation* half of RAG, Sprint 5 extended ingestion beyond raw text,
Sprint 6 improved retrieval quality itself, Sprint 7 added streaming,
Sprint 8 added observability, and Sprint 9 (this repo) added the demo
UI — the last item in the original roadmap.

- [x] RAG pipeline: document ingestion, chunking, embedding, `VectorStore` port + FAISS adapter
- [x] Auth (API keys / OAuth2) and rate limiting
- [x] Answer generation: `POST /documents/ask` — LangChain LCEL chain (retriever + prompt + local SLM)
- [x] Document loaders (PDF, Markdown, TXT, HTML) for ingestion beyond raw text
- [x] Hybrid retrieval, query routing (LangGraph), re-ranking
- [x] Streaming responses (SSE) for `/documents/ask`
- [x] Observability: request tracing (OpenTelemetry -> Jaeger), metrics (Prometheus), dashboards (Grafana)
- [x] A minimal demo UI (Streamlit) beyond Swagger

Not planned, evaluated and explicitly deferred:

- External LLM provider adapter (see [ADR-0002](docs/adr/0002-llm-runtime-ollama-vs-external-apis.md) revisit triggers) — no concrete need yet for quality beyond local open-weight models.
- Async ingestion / message broker (see [ADR-0009](docs/adr/0009-async-ingestion-message-broker.md)) — no concrete need yet for decoupled/fan-out processing.

## Contributing

1. Fork and branch from `main`.
2. Run `make check` before opening a PR — CI enforces the same gate.
3. For non-trivial architectural choices, add an ADR under `docs/adr/`.

## License

[MIT](LICENSE)
