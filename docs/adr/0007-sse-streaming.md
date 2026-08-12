# ADR-0007: Streaming Answers — SSE, `stream` Request Field, Same Graph

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0004: LangChain for Answer Generation](0004-langchain-for-answer-generation.md), [ADR-0006: Hybrid Retrieval & Query Routing](0006-hybrid-retrieval-and-query-routing.md) |

## Context

`POST /documents/ask` waited for the full generated answer before
responding. For a chat-style endpoint, users expect tokens to appear as
they're generated, not a multi-second blocking wait.

## Decision Drivers

- Match the streaming UX every major LLM provider API offers today.
- Don't restructure the query-routing graph (ADR-0006) to get it —
  a second, streaming-specific code path duplicating the routing/
  retrieval/rerank logic would be a maintenance liability.
- No new dependency if the existing stack already covers it.

## Options Considered

### Transport: Option A — Server-Sent Events

**Pros**
- Unidirectional (server → client) is all this needs; SSE is simpler
  than WebSocket for that shape and works over plain HTTP.
- `StreamingResponse` + `media_type="text/event-stream"` ships in
  FastAPI/Starlette already — no new dependency.
- Matches how OpenAI/Anthropic stream chat completions — a pattern API
  consumers already know.

### Transport: Option B — WebSocket

**Pros**
- Supports bidirectional communication (client could send follow-ups
  mid-stream, cancel generation, etc.).

**Cons**
- Nothing today needs bidirectional communication — the client just
  wants tokens as they arrive. WebSocket's extra complexity (connection
  lifecycle, framing) would be unearned.

### Request shape: Option A — `stream: bool` field on the existing `AskRequest`

**Pros**
- One endpoint, one schema — matches the OpenAI-style convention
  (`{"stream": true}` in the request body) API consumers already expect.
- No new route to document or keep behaviorally in sync with `/ask`.

### Request shape: Option B — separate `POST /documents/ask/stream` endpoint

**Cons**
- Two endpoints doing the same routing/retrieval/generation, diverging
  over time, for a distinction (streamed vs. not) that's naturally a
  request-time choice, not a different resource.

## Decision

**SSE, toggled via `AskRequest.stream`, reusing the unmodified query
graph from ADR-0006.**

Verified directly (LangGraph's streaming API moves fast) before
implementing: `compiled_graph.astream(state, stream_mode=["messages", "values"])`
yields `("messages", (chunk, metadata))` tuples — where
`metadata["langgraph_node"]` names the node that produced the token —
interleaved with `("values", full_state_dict)` snapshots after every
node. This means:

- `GenerationService.ask_stream()` filters token chunks to only the
  answer-producing nodes (`generate`, `direct_answer`); the internal
  `classify_query`/`rerank` LLM calls also stream tokens (LangGraph
  streams from every node that calls a chat model), but those are
  filtered out by node name before ever reaching the client.
- The last `"values"` snapshot before the stream ends carries the
  complete final state (`documents`) — that's where the final `sources`
  SSE event comes from, with no separate retrieval call needed.
- `query_graph.py`'s node functions are completely unchanged; only
  `GenerationService` gained a second method (`ask_stream`, alongside
  the existing `ask`) that drives the same `self._graph` differently.

**Errors mid-stream become a final `event: error` SSE event**
(`backend/api/sse.py`), not an HTTP 500 — once `StreamingResponse` has
sent its first bytes, HTTP headers are already committed and the
response can't switch to a JSON error body. The alternative (letting the
exception propagate and the connection die) gives the client no signal
at all that something went wrong.

## Revisit Triggers

- A client needs to cancel an in-flight generation, or send follow-up
  input mid-stream → that's bidirectional, and is what WebSocket is for;
  revisit Option B above.
- Multiple concurrent streamed requests per API key need to share a
  rate-limit budget mid-stream (today's `InMemoryRateLimiter`, ADR-0003,
  only gates the request at start) → rate limiting would need to account
  for stream duration/token volume, not just request count.

## Consequences

- `backend/api/sse.py` is a small, generic SSE-formatting module — reusable
  if another endpoint ever needs to stream.
- `GenerationService.ask()` and `.ask_stream()` share `_initial_state`
  and `_sources` helpers; the routing/retrieval/rerank/generate logic
  itself lives in exactly one place (`llm/routing/query_graph.py`),
  regardless of which method drives the graph.
- The installed `langgraph` type stubs don't fully model the tuple shape
  multi-mode `astream()` actually yields (verified empirically, not just
  assumed from the stubs) — `generation_service.py` casts the stream to
  the verified shape with a comment explaining why, rather than fighting
  the stub gap with scattered per-line `type: ignore`s.
