"""Runtime configuration for the Konsole.ai MCP server.

Read from `KONSOLE_`-prefixed environment variables set by the MCP
client's per-server config (e.g. Claude Desktop's `env` block) at
subprocess spawn time -- there is no `.env` file involved, unlike
`backend/config/settings.py`'s `Settings`, since this is a short-lived
subprocess, not a long-running app. See docs/adr/0016-mcp-server-support.md.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MCPServerConfig:
    api_base_url: str
    api_key: str
    timeout_seconds: float


def load_config() -> MCPServerConfig:
    return MCPServerConfig(
        api_base_url=os.environ.get("KONSOLE_API_BASE_URL", "http://localhost:8000"),
        api_key=os.environ.get("KONSOLE_API_KEY", "dev-local-key"),
        # `ask` can chain up to 3 sequential LLM calls (classify -> rerank
        # -> generate, see llm/routing/query_graph.py) -- verified live
        # against the docker-compose stack that a 30s default timed out
        # here even though every individual call succeeds well within it.
        timeout_seconds=float(os.environ.get("KONSOLE_API_TIMEOUT_SECONDS", "90")),
    )
