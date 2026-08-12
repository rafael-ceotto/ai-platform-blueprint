# ADR-0008: Observability — OpenTelemetry Tracing, Prometheus Metrics, Grafana Dashboards

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0006: Hybrid Retrieval & Query Routing](0006-hybrid-retrieval-and-query-routing.md), [ADR-0007: SSE Streaming](0007-sse-streaming.md) |

## Context

Structured JSON logging (`observability/logging/setup.py`) has existed
since Sprint 1, but there was no way to answer "how long did this
request actually take, and where," or "how is the system performing
under load, right now, at a glance." This closes both gaps: distributed
tracing (per-request spans across the API and its calls to Ollama) and
metrics + dashboards (request rate, error rate, latency).

## Decision Drivers

- Match the standard senior-platform-engineering observability story:
  logs + traces + metrics, correlated.
- No half-measures — this is a portfolio piece; a stubbed `/metrics`
  endpoint with nothing scraping it doesn't demonstrate anything.
- Verify library/image choices directly — this ecosystem moves fast
  (confirmed: Jaeger v1 reached end-of-life on 2025-12-31 during
  research for this ADR).

## Options Considered

### Tracing: Option A — OpenTelemetry SDK, manual instrumentation, OTLP -> Jaeger v2

**Pros**
- Vendor-neutral, industry-standard API; `opentelemetry-instrumentation-fastapi`
  and `opentelemetry-instrumentation-httpx` give free spans for every
  incoming request and every outgoing call to Ollama, with correct
  parent/child nesting, no hand-written spans required for v1.
- Manual SDK setup (build a `TracerProvider`, call
  `FastAPIInstrumentor.instrument_app(app, tracer_provider=...)`) is
  explicit and testable, consistent with this codebase's existing
  dependency-injection style, rather than the `opentelemetry-instrument`
  CLI wrapper (would require changing the Dockerfile's entrypoint, and
  is documented to break under `--reload`).
- Jaeger v2 (`jaegertracing/jaeger:2.20.0`) speaks OTLP natively —
  no separate OTel Collector needed for a single-service local stack.

**Cons**
- Jaeger v1's familiar `jaegertracing/all-in-one` image is dead
  (EOL 2025-12-31); had to verify the v2 image name/tag/ports directly
  rather than trust memorized tutorials, several of which still show v1.

### Metrics: Option A — `prometheus-fastapi-instrumentator` + Prometheus + Grafana

**Pros**
- Actively maintained (v8.1.0, July 2026, ~3.5M weekly downloads).
  `Instrumentator().instrument(app).expose(app)` gives the standard RED
  metrics (`http_requests_total`, `http_request_duration_seconds`,
  `http_requests_inprogress`) with zero custom metric code.
- Prometheus + Grafana as new `docker-compose.yml` services, with
  Grafana's datasource and one starter dashboard provisioned via
  bind-mounted config (`infra/grafana/provisioning/`), means
  `docker compose up` alone produces a working dashboard — no manual
  Grafana click-ops.

**Cons**
- Three more containers in `docker-compose.yml` (`jaeger`, `prometheus`,
  `grafana`), on top of `api` and `ollama`.

## Decision

**OpenTelemetry (FastAPI + httpx instrumentation) exporting via
OTLP/gRPC to Jaeger v2, and `prometheus-fastapi-instrumentator`
exposing `/metrics` for Prometheus, visualized in a provisioned Grafana
dashboard.** No hand-rolled custom business metrics in this pass — the
default RED metric set is already the standard story; custom metrics
(e.g. "queries routed to direct-answer vs. retrieve") are a cheap,
natural follow-up once this plumbing exists.

**Both `Settings.TRACING_ENABLED` and `Settings.METRICS_ENABLED`
default to `False`, and are only flipped `true` in
`docker-compose.yml`'s `api` service environment** — mirroring the
existing pattern for `OLLAMA_BASE_URL` (localhost default, compose
overrides to the container hostname). This isn't just style: `tests/`
calls `create_app()` up to 8 times in a single pytest process, and both
the Prometheus client's default `CollectorRegistry` and OpenTelemetry's
`TracerProvider` are process-global singletons — instrumenting a second
app against either raises (Prometheus) or silently discards the second
provider with a warning (OpenTelemetry). Gating both behind settings
that default off means tests and bare `make run` never touch that
global state at all; only the single `create_app()` call inside the
live `api` container ever does.

**Structured logs now carry `trace_id`/`span_id`** (top-level fields,
`observability/logging/setup.py`'s `JSONFormatter`) whenever a valid
OpenTelemetry span is active, via
`trace.get_current_span().get_span_context()` — a no-op when tracing is
disabled or no span is active, since that call returns an invalid span
context in both cases. This is what makes "find the trace for this
error log line" actually possible.

## Revisit Triggers

- Custom business metrics (query routing decisions, rerank duration,
  retrieval candidate counts) become worth the coupling between
  `llm/routing/query_graph.py` and the metrics layer.
- Multi-service deployment (beyond `api` + `ollama`) needs a real OTel
  Collector in front of Jaeger for fan-in/sampling/processing, instead
  of exporting directly.
- Jaeger's in-memory storage (the default in all-in-one mode) isn't
  enough — traces don't survive a container restart — and a real
  backend (Elasticsearch/Cassandra) is needed.

## Consequences

- `observability/tracing/setup.py` and `observability/metrics/setup.py`
  are small, single-purpose modules — `instrument_app(app, settings)`
  in each, called from `backend/main.py`'s `create_app()`.
- New `infra/` directory holds Prometheus and Grafana config, kept
  separate from the Python-package top-level directories
  (`backend`/`ingestion`/`retrieval`/`llm`/`observability`) since it's
  infra config, not application code.
- Six new dependencies (`prometheus-fastapi-instrumentator`,
  `opentelemetry-api`/`sdk`/`instrumentation-fastapi`/
  `instrumentation-httpx`/`exporter-otlp-proto-grpc`) and three new
  `docker-compose.yml` services. `docker compose up -d --build` is the
  only setup step — Jaeger UI, Prometheus, and the provisioned Grafana
  dashboard are all live immediately after.
