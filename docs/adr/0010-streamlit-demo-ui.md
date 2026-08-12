# ADR-0010: Minimal Demo UI — Streamlit, Separate Deployable, httpx2 for SSE

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0007: SSE Streaming](0007-sse-streaming.md), [ADR-0008: Observability](0008-observability-tracing-metrics-dashboards.md) |

## Context

Everything built so far (ingestion, hybrid search, streaming RAG
answers with cited sources) was only reachable via `curl` or Swagger.
This is the last item in the confirmed roadmap: a minimal demo UI that
shows the whole stack working, beyond `/docs`.

## Decision Drivers

- Show off what already exists (ask + streaming + sources, search,
  ingest/upload) without duplicating any business logic — the UI is a
  thin client over the existing API, nothing more.
- Stay consistent with how every other piece of local infra in this
  blueprint is run: `docker compose up` and it's just there (Jaeger,
  Prometheus, Grafana all followed this pattern in ADR-0008).
- Keep it genuinely minimal — this is the intentionally lightest
  sprint; don't over-invest in UI polish, multipage navigation, or
  strict type-checking parity with the backend.

## Decision

**A Streamlit app in a new top-level `ui/` directory, run as its own
`docker-compose.yml` service, talking to the API only over HTTP.**

- `ui/app.py` (rendering) + `ui/api_client.py` (all HTTP calls) —
  mirrors the backend's services-vs-endpoints separation and keeps
  `api_client` mockable for a smoke test without a live API.
- Own `ui/requirements.txt` (`streamlit`, `httpx2`) and own
  `ui/Dockerfile`, entirely separate from the backend's
  `pyproject.toml`/`Dockerfile`. Verified this matters, not just
  stylistic: installing Streamlit into the same virtualenv as the
  backend downgrades `starlette` (Streamlit pins `starlette<1.4.0`),
  because Streamlit happens to also depend on FastAPI/Starlette
  internally. The two apps must ship as separate images with
  independent dependency resolution — confirmed the existing 79
  backend tests still pass under the downgraded `starlette` in the
  shared *local dev* venv, but that's incidental, not something to
  rely on; production images stay isolated regardless.
- **`httpx2`**, not `httpx`, for `ui/api_client.py`'s HTTP calls.
  Verified this isn't a random substitution: Pydantic Services has
  taken over stewardship of `httpx` under the new name, and this
  repo's own test output already carries Starlette's own deprecation
  notice recommending the switch. `httpx2.Client().sse(url,
  method="POST", json=...)` natively parses Server-Sent Events into
  `ServerSentEvent(event, data)` objects, a direct fit for consuming
  `backend/api/sse.py`'s output without hand-rolled line parsing. This
  is scoped to the new `ui/` code only — the backend's existing
  `httpx` dependency is unrelated and untouched by this ADR.
  `st.write_stream` renders the token generator with a typewriter
  effect and returns the full text once exhausted; the final `done`
  event's `sources` are captured via a closure-scoped dict rather than
  being part of the streamed text.
- **Three tabs (`st.tabs`), one script** — Ask (streaming answer +
  cited sources), Search (raw hybrid results), Ingest (raw text or
  file upload) — not a Streamlit multipage app. The whole thing is
  small enough that page-level navigation would be overhead for no
  benefit.
- **`ui/` is intentionally excluded from the strict `mypy` scope**
  (`Makefile`'s `typecheck` target is unchanged:
  `backend ingestion retrieval llm observability`). `ruff check .` is
  repo-root scoped already, so basic lint/format discipline still
  applies with no config change. One `streamlit.testing.v1.AppTest`
  smoke test (`tests/test_ui_app.py`) covers "the app loads and
  renders its tabs without exception," plus one interaction test
  (search, with `api_client.search` mocked) — deliberately not
  exhaustive coverage of all three tabs, matching the "minimal" brief.

## Revisit Triggers

- The UI grows beyond a few screens worth of logic per tab -> split
  into a Streamlit multipage app.
- The UI needs to demonstrate anything beyond "call the existing API
  and render the result" (e.g. client-side state beyond a single
  session, auth beyond a pasted API key) -> reconsider Streamlit vs. a
  small dedicated frontend framework.

## Consequences

- New `docker-compose.yml` service `ui`, depending on `api` being
  healthy, exposed at `http://localhost:8501`.
- No backend code changes; the API surface and its tests are
  untouched by this sprint.
- Anyone cloning the repo gets ingestion, search, and streaming RAG
  answers with sources in a browser, zero-config against the default
  stack, immediately after `docker compose up -d --build`.
