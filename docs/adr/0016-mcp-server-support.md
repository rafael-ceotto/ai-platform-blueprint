# ADR-0016: MCP Server Support — stdio Transport, HTTP Wrapper Over the Existing API

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-13 |
| **Deciders** | Konsole.ai team |
| **Related** | [ADR-0010: Streamlit Demo UI](0010-streamlit-demo-ui.md), [ADR-0003: API Key Auth and Rate Limiting](0003-api-key-auth-and-rate-limiting.md), [ADR-0014: Kubernetes and Cloud Deployment](0014-kubernetes-and-cloud-deployment.md) |

## Context

MCP (Model Context Protocol) standardizes how LLM tools/clients (e.g.
Claude Desktop) discover and call external capabilities. Konsole.ai
could plug into MCP as a **server** (exposing its own RAG capabilities
as tools other MCP clients can call) or as a **client** (consuming
external MCP servers inside its own generation pipeline). The explicit
priority, consistent with ADR-0014's "no live cloud spend" stance for
this portfolio project, was avoiding any new running cost.

## Decision Drivers

- **Zero marginal cost.** No new hosting, no new infra, nothing billed
  per request.
- Reuse existing auth/rate-limiting/observability (ADR-0003, ADR-0015)
  rather than re-implementing them in a second surface.
- Match the project's established posture for non-backend consumers:
  `ui/` talks to the API only over HTTP and is never allowed to import
  backend code directly (ADR-0010).
- Don't trust fast-moving-library facts from memory — verify the real
  installed `mcp` SDK source before writing code, the same discipline
  used for LangChain/LangGraph/Jaeger throughout this project's history.

## Decision

**Konsole.ai is an MCP *server*, stdio transport only — not a client,
not a remote HTTP/SSE server.**

stdio means the server is a local subprocess, spawned on demand by
whatever MCP client the user configures (e.g. Claude Desktop's
`claude_desktop_config.json`). There's nothing to host: $0 marginal
cost, no new attack surface exposed to the network. Becoming an MCP
*client* was rejected for this pass — it would mean depending on
external MCP servers of unknown/variable cost, working against the
project's local-first stance (ADR-0002); noted below as a possible
future direction, not built now. Remote HTTP/SSE transport was also
rejected — that's the transport that would actually need hosting to be
reachable by anyone but the local user, which is exactly the cost this
ADR avoids.

### Architecture: thin HTTP wrapper over the existing API, not in-process

New top-level directory `mcp_server/` — architecturally a sibling to
`ui/`, an external consumer of the FastAPI backend, not part of the
`backend/ingestion/retrieval/llm/observability` package graph.

`mcp_server/api_client.py` talks to the already-running `api` service
over plain HTTP (`ask`, `search`, `ingest_text`), mirroring
`ui/api_client.py`'s pattern (ADR-0010) — using core `httpx`
(async), not `httpx2`, since MCP tool calls are simple request/response
with no SSE involved. **Rejected alternative**: constructing
`GenerationService`/`IngestionService` in-process inside the MCP
subprocess. That would mean a second, divergent copy of application
state — its own `FaissVectorStore` handle, no shared rate limiter, no
`X-API-Key` enforcement, no LLM trace recording (ADR-0015) — strictly
worse than one HTTP call to the authoritative running `api` service.
The HTTP wrapper gets auth and rate limiting for free, by construction.

Three tools for v1, wrapping the three non-streaming-relevant REST
endpoints (`backend/api/v1/endpoints/documents.py`):
- `ask(query, top_k)` → `POST /documents/ask` (`stream: false`)
- `search(query, top_k)` → `POST /documents/search`
- `ingest_text(text, metadata)` → `POST /documents` (`stream: false`)

File upload (`POST /documents/upload`) is deferred — binary content
over MCP tool arguments is awkward (base64), not essential for v1.

### Configuration

Plain `KONSOLE_`-prefixed environment variables
(`KONSOLE_API_BASE_URL`, `KONSOLE_API_KEY`,
`KONSOLE_API_TIMEOUT_SECONDS`), read by `mcp_server/config.py` at
subprocess spawn time — not `pydantic-settings`/`Settings`, since this
is a short-lived subprocess configured entirely by whatever `env` block
the MCP client passes, not a long-running app reading a `.env` file.
The `KONSOLE_` prefix keeps a multi-server MCP client config
self-documenting.

### Dependency placement — verified, not assumed

Installed `mcp[cli]` (confirmed real package name, version `2.0.0`)
into the dev venv and diff-checked `pip list` / ran `pip check` before
deciding anything, the same lesson ADR-0010 learned the hard way with
Streamlit downgrading `starlette`. Result: **clean** — no version
changes to `fastapi`, `starlette`, `httpx`, `pydantic`,
`pydantic-settings`, or `uvicorn`, and `pip check` reported no broken
requirements. `mcp` targets modern FastAPI/Starlette itself, so this
was the expected (lower-risk-than-Streamlit) outcome. `mcp` also ships
`py.typed`, so no `mypy` override was needed (unlike `faiss`/`rank_bm25`).

Added as a new `[project.optional-dependencies].mcp` extra in
`pyproject.toml` — the same mechanism as the existing `ui` extra — not
full isolation like `ui/`'s separate `requirements.txt`/Dockerfile.
`ui/` needed full isolation because it's a standing container in
`docker-compose.yml`; `mcp_server/` is never deployed or containerized,
it's a subprocess the MCP client spawns on the developer's own machine
using whatever Python environment that client is configured to invoke.
`mcp_server` is included in the strict `mypy` scope (unlike `ui/`,
whose exclusion was justified by Streamlit's own untyped/dynamic API —
`mcp_server/` is an ordinary typed HTTP-wrapper module with no such
excuse).

### Verified real SDK API (not the unverified rumor from a preliminary web summary)

Confirmed by reading the actual installed `mcp==2.0.0` source
(`site-packages/mcp/server/mcpserver/server.py`,
`site-packages/mcp/client/client.py`):
- `from mcp.server.mcpserver import MCPServer` — `MCPServer("Konsole.ai")`.
- `@mcp.tool()` decorator on a type-hinted (sync or async) function with
  a docstring auto-generates the JSON schema and description.
- `mcp.run()` — synchronous, defaults to `transport="stdio"`.
- `mcp dev <file>` is a real CLI subcommand (`mcp/cli/cli.py`), used for
  local interactive inspection — the rumored command turned out to be
  accurate, but this was confirmed rather than assumed.
- `mcp.client.Client(server_instance)` connects in-process (no
  subprocess/stdio) when given an `MCPServer`/`Server` object directly
  — `async with Client(mcp) as client: await client.call_tool(name, args)`
  / `await client.list_tools()`. This is what `tests/test_mcp_server.py`
  uses, so the test suite never spawns a subprocess or needs a live API.
  `CallToolResult` has `.content` (list of content blocks), `.is_error`,
  and `.structured_content` (the tool's return value, JSON-serialized) —
  a tool that raises is caught by `MCPServer` itself and surfaced as
  `CallToolResult(is_error=True)`, not a crash, so the tool functions in
  `mcp_server/server.py` don't need their own try/except around
  `api_client` calls.

### Launch

Both work: `python -m mcp_server.server` (what `mcp dev` needs — it
takes a file path) and a `[project.scripts]` console entry
(`konsole-mcp-server = "mcp_server.server:main"`, for real MCP client
configs after `pip install -e ".[mcp]"`). A sample
`claude_desktop_config.json` block:

```json
{
  "mcpServers": {
    "konsole-ai": {
      "command": "<path-to-venv>/Scripts/konsole-mcp-server.exe",
      "env": {
        "KONSOLE_API_BASE_URL": "http://localhost:8000",
        "KONSOLE_API_KEY": "dev-local-key"
      }
    }
  }
}
```

## Revisit Triggers

- A file-upload MCP tool becomes worth the base64-encoding complexity.
- A concrete use case appears for Konsole.ai as an MCP *client*
  (consuming an external server) — pick specific, ideally free,
  external servers at that point rather than speculating now.
- Remote reachability (HTTP/SSE transport, hosting) becomes worth its
  cost — e.g. a specific interview process wants to connect to a
  running Konsole.ai MCP server without SSH/local setup. Same revisit
  logic as ADR-0014's cloud-deployment trigger.

## Consequences

- New `mcp_server/` package (`__init__.py`, `config.py`, `api_client.py`,
  `server.py`), `tests/test_mcp_server.py`, a new `mcp` extra in
  `pyproject.toml`, a `konsole-mcp-server` console script, `mcp_server`
  added to the strict `mypy`/coverage scope, and a `make mcp-dev`
  convenience target running `mcp dev mcp_server/server.py`.
- No backend code changes — the REST API surface and its tests are
  untouched by this ADR, matching the pattern ADR-0010 set for `ui/`.
- Anyone with the repo installed (`pip install -e ".[mcp]"`) and the
  `docker compose` stack running can point an MCP client at
  `konsole-mcp-server` and get `ask`/`search`/`ingest_text` as callable
  tools, at zero additional cost.
