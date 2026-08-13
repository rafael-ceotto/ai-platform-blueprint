"""MCP stdio server exposing Konsole.ai's ask/search/ingest_text
capabilities as MCP tools.

Spawned as a local subprocess on demand by an MCP client (e.g. Claude
Desktop) -- stdio transport only, no hosting, $0 marginal cost. Talks
to the already-running FastAPI backend over HTTP (`mcp_server/api_client.py`)
rather than constructing backend services in-process. See
docs/adr/0016-mcp-server-support.md.
"""

from typing import Any

from mcp.server.mcpserver import MCPServer

from mcp_server import api_client
from mcp_server.config import load_config

mcp = MCPServer("Konsole.ai")
_config = load_config()


@mcp.tool()
async def ask(query: str, top_k: int | None = None) -> dict[str, Any]:
    """Ask a question answered by Konsole.ai's RAG pipeline: retrieves
    relevant document chunks (or ingestion-log entries) and generates a
    grounded answer with cited sources."""
    return await api_client.ask(
        _config.api_base_url, _config.api_key, query, top_k, _config.timeout_seconds
    )


@mcp.tool()
async def search(query: str, top_k: int | None = None) -> dict[str, Any]:
    """Hybrid (semantic + keyword) search over Konsole.ai's ingested
    document collection. Returns ranked chunks, no generation."""
    results = await api_client.search(
        _config.api_base_url, _config.api_key, query, top_k, _config.timeout_seconds
    )
    return {"results": results}


@mcp.tool()
async def ingest_text(text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ingest raw text into Konsole.ai: chunk, embed, and store it so it
    becomes searchable/askable."""
    return await api_client.ingest_text(
        _config.api_base_url, _config.api_key, text, metadata or {}, _config.timeout_seconds
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
