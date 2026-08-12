# ADR-0013: ETL Progress Streaming + a Queryable Ingestion Log

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-12 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0006: Hybrid Retrieval & Query Routing](0006-hybrid-retrieval-and-query-routing.md), [ADR-0007: SSE Streaming](0007-sse-streaming.md) |

## Context

Ingestion (chunk -> embed -> store) is effectively an ETL job, but it
was a black box: the UI sent one request and waited for a single JSON
response. Two asks: show it running, step by step, in the browser; and
keep a durable record of each run that can be asked about later in
natural language, optionally by referencing the document ID directly.

## Decision

**ETL progress reuses the SSE machinery already built for
`/documents/ask` (ADR-0007)** — `backend/api/sse.py` needed zero
changes. `IngestionService.ingest_document_stream()` is the single
source of truth (an async generator yielding
`{"type": "step", "step": "chunking"|"embedding"|"storing"}`, plus a
`"loading"` step the endpoint layer prepends for file uploads before
`load_document()` runs); `ingest_document()` is now a thin wrapper that
drains the same generator. `POST /documents` and `/documents/upload`
gained a `stream` toggle (JSON field / form field respectively),
mirroring `AskRequest.stream` exactly. Steps are coarse — one event per
ETL stage, not per chunk — matching "each stage," not chunk-level
noise.

**The ingestion log is a second `FaissVectorStore` instance, not new
storage code.** Every completed run (including empty/error runs)
becomes one entry: `page_content` is a natural-language rendering
("Ingestion log for document {id}. Source: {type} ({filename}).
Completed in {ms}ms, {n} chunks, status: {status}."), embedded the same
way content chunks are; the structured fields live in metadata. Because
it's a real `HybridVectorStore`, it gets BM25 + vector search "for
free" via the existing `build_hybrid_retriever`/`with_rrf_scores`
(`retrieval/retriever/hybrid.py`) — zero new retrieval code, and the
resulting `Document`s already carry the `chunk_id`/`score` metadata
`GenerationService._sources()` expects (set generically by
`VectorStoreRetriever`/`with_rrf_scores`, not content-specific).

**`llm/routing/query_graph.py` gained a third route: `log`.**
`classify_query` is now a 3-way classifier (DIRECT / RETRIEVE / LOG);
`log_retrieve` -> `log_generate` mirrors the content path but skips
rerank (log entries are typically few and precise — often an exact
document-ID match) and uses a new prompt
(`llm/prompts/log_answer_prompt.py`, includes the same
"answer in the question's language" line added to the other
answer-generating prompts this session). Empty results skip the LLM
via a fixed `NO_LOG_ANSWER`, mirroring `no_context_answer`.
`build_query_graph()` gained a `log_vector_store` parameter; `/documents/ask`
itself needed **no new code path** — the `log` route is just another
branch the same graph and the same `ask()`/`ask_stream()` already
drive.

**No dedicated `GET /documents/{id}/ingestion` endpoint.** Passing an
ID is just part of the natural-language question — BM25 matches the
literal ID substring reliably against the log's embedded text and
metadata, so a plain `/ask` call already satisfies "look this up by
ID" without a second API surface to build and maintain.

**UI**: `ui/api_client.py` gained `ingest_text_stream()`/
`upload_file_stream()` (same shape as `ask_stream()`); the old blocking
`ingest_text()`/`upload_file()` were deleted rather than kept alongside
unused, once nothing called them. `ui/app.py`'s Ingest tab renders
progress via `st.status(expanded=True)` — one line per completed step,
label/state updated as events arrive — Streamlit's built-in
step-tracker pattern.

## Revisit Triggers

- Ingestion volume grows enough that a dedicated exact-ID lookup
  endpoint becomes worth the extra API surface (bypassing the LLM for
  that one case).
- The log index grows large enough that fusing it into the same
  retrieval call as content search becomes tempting — resist that;
  keeping them separate is what stops "what is FastAPI" from ever
  surfacing an ingestion-log fragment.

## Consequences

- `IngestionService.__init__` and `build_query_graph()`/
  `GenerationService.__init__` all gained a required parameter
  (`log_vector_store`) — every call site, including tests, needed
  updating.
- New `LOG_VECTOR_STORE_PATH` setting (default `./data/ingestion_logs`),
  same `api_data` Docker volume as the content index — no
  `docker-compose.yml` changes needed.
- Every ingestion, including ones that produce zero chunks or fail
  file-type detection, now leaves a record — useful for debugging a
  "why didn't my document show up in search" report from a user.
