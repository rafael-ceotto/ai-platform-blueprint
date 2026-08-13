# ADR-0015: LLM Tracing & Cost/Token/Latency Observability

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-13 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0002: LLM Runtime](0002-llm-runtime-ollama-vs-external-apis.md), [ADR-0006: Hybrid Retrieval & Query Routing](0006-hybrid-retrieval-and-query-routing.md), [ADR-0008: Observability](0008-observability-tracing-metrics-dashboards.md), [ADR-0013: ETL Progress & Queryable Ingestion Log](0013-etl-progress-and-queryable-ingestion-log.md)

## Context

ADR-0008 already covers request-level tracing/metrics (OpenTelemetry ->
Jaeger/Prometheus). What it doesn't capture is anything specific to
*LLM calls themselves*: which prompt was sent, what came back, how many
tokens were spent, and what it cost — the Langfuse-style observability
idea. Separately, a RAGAS-style automated eval harness (faithfulness,
context precision against a golden Q&A set) was also on the table. The
two turned out not to be independent: an eval harness needs exactly the
same per-call record (question, retrieved context, generated answer,
tokens) that a cost/latency dashboard needs. This ADR covers **Phase
1 only — capture and expose that trace record.** The eval harness
(Phase 2) is a revisit trigger below, not built here.

## Decision Drivers

- `GenerationService` already routes every `/documents/ask` request
  through one compiled LangGraph graph
  (`llm/routing/query_graph.py`), so whatever captures LLM calls should
  hook in once, centrally — not be duplicated across
  `classify_query`/`direct_answer`/`rerank`/`generate`/`log_generate`.
- Nothing in this project has needed a SQL database before (FAISS +
  JSON sidecars for vectors, per ADR-0001/0013). A trace is inherently
  small structured rows with aggregate queries (cost totals, latency
  percentiles, breakdown by node) — a genuinely different shape of data
  than "documents to search," worth its own justified exception rather
  than force-fitting into FAISS.
- Cost tracking only matters once `LLM_PROVIDER` (ADR-0002's own
  revisit trigger) points at a paid API — building the mechanism now,
  defaulting every model's price to $0, means it's already correct on
  that day instead of needing to be retrofitted.
- CI has never depended on a live Ollama daemon (`FakeListChatModel`/
  `FakeOllamaClient` are used everywhere in
  `tests/test_generation_service.py` specifically to avoid that) — an
  eval harness that requires real model calls to score faithfulness
  would be the first thing to break that invariant, which is exactly
  why it's deferred rather than bundled into this same change.

## Options Considered

### Storage: SQLite vs. JSONL

**SQLite (chosen)** — one file (`Settings.LLM_TRACE_DB_PATH`, default
`./data/llm_traces.db`), stdlib `sqlite3`, no new service or
dependency. Real aggregate queries (`SUM`, `AVG`, `GROUP BY`) for cost
totals, latency percentiles, and per-node breakdowns, without loading
the whole trace history into memory as it grows. Lives on the same
`api_data` Docker volume that already covers `./data` — no compose
changes needed, same pattern ADR-0013 used for the ingestion-log FAISS
store.

**JSONL** — simpler to eyeball by hand, but every aggregate the
dashboard needs (percentiles, cost-by-node) would mean reading and
parsing the whole file on every request. Rejected: the dashboard is
exactly the kind of read pattern SQL exists for.

### Capture mechanism: LangChain callback vs. manual instrumentation

**A LangChain `AsyncCallbackHandler` (chosen)**, attached per-request
via `config={"callbacks": [...]}` on `self._graph.ainvoke()`/
`.astream()`. LangGraph already tags every callback invocation with the
node that triggered it (`metadata["langgraph_node"]`) — the same
mechanism `GenerationService.ask_stream` already relies on to filter
which tokens reach the client — so one handler transparently sees every
chat-model call the graph makes, correctly attributed to its node, with
zero changes to `llm/routing/query_graph.py` itself.

**Manual instrumentation** (wrapping each `chain.ainvoke()` call in
`query_graph.py` with timing/logging code) was rejected: it would
duplicate the same boilerplate across five call sites and get out of
sync as nodes are added or changed.

## Decision

**Phase 1 (this ADR): capture every LLM call as an `LLMTrace`
(`observability/llm_traces/`) via a per-request callback handler,
persisted to SQLite, exposed read-only via `GET /observability/traces`
and `GET /observability/summary`, and surfaced in a new Streamlit
"Observability" tab.** Cost is estimated via a static per-model pricing
table (`observability/llm_traces/pricing.py`) that defaults unknown
models — i.e. every local Ollama model today — to $0.00.

Jaeger/Prometheus/Grafana dashboards are deliberately **not** embedded
inside the new Streamlit tab: Streamlit has no native widget for
rendering another tool's full UI, and the only way to approximate it
(`st.components.v1.iframe`) is fragile — Grafana blocks iframe
embedding by default (`X-Frame-Options`) unless explicitly configured,
and reproducing their dashboards via Streamlit's native charts would
mean rebuilding tools that already exist. The Observability tab shows
only this project's own trace data, queried through the two new REST
endpoints, the same HTTP-only pattern the rest of `ui/` already follows
(ADR-0010).

## Revisit Triggers

Build Phase 2 — the RAGAS-style eval harness — as its own change,
reading from `LLMTraceStore` (tagging eval runs with `is_eval=True` or
similar so they're distinguishable from real traffic), when there's
time to also resolve:

- Whether eval runs against a real Ollama daemon belong in CI as a
  gating check, given CI has no such dependency today, or stay a local
  `make eval` command for now.
- What the golden Q&A dataset and its corpus are (a small, isolated
  fixture set — not the user's live index — to keep eval deterministic
  regardless of what's actually been ingested).

Add real per-model pricing entries to `MODEL_PRICING` when `LLM_PROVIDER`
(ADR-0002) is pointed at a paid API — the cost-tracking mechanism itself
needs no changes on that day, only data.

## Consequences

- New dependency-free storage layer (`sqlite3`, stdlib) — the project's
  first SQL usage, justified above rather than defaulted into.
- `GenerationService.__init__` gains a required `llm_trace_store`
  param; every construction site (`backend/api/v1/endpoints/documents.py`,
  and every test building a `GenerationService`) must supply one.
- Two new read-only, authenticated REST endpoints under
  `/api/v1/observability/*`.
- No new Docker services, volumes, or compose changes.
- **Expected behavior, not a bug**: the trace store is cumulative and
  persists across container restarts (it lives on the `api_data` Docker
  volume, same as the FAISS indexes) — it is not scoped to a browser
  session, and there's no cache involved anywhere in this path. Opening
  the Streamlit Observability tab and clicking "Load / refresh" shows
  every `/documents/ask` call ever made against that volume, including
  ones from `curl`, the MCP server (ADR-0016), or a previous session —
  not just calls made since the tab was opened. It's also normal to see
  traces with **zero ingested documents**: every `/ask` request routes
  through `classify_query` first (see ADR-0006), which is itself an LLM
  call and gets recorded regardless of whether anything was ever
  ingested or whether the query ultimately finds any context.
