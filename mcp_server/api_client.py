"""Thin async HTTP client for the Konsole.ai API, used by mcp_server/server.py.

Talks to the already-running FastAPI backend only over HTTP -- the same
external-consumer posture `ui/` takes toward the API
(docs/adr/0010-streamlit-demo-ui.md) -- rather than constructing
backend services in-process, so every MCP tool call sees the same
authoritative FAISS index / rate limiter / API-key enforcement / LLM
trace recording as every other client. See docs/adr/0016-mcp-server-support.md.
"""

from typing import Any

import httpx


class ApiError(RuntimeError):
    """Raised when the API returns a non-2xx response."""


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_error:
        raise ApiError(f"{response.status_code}: {response.text}")


async def ask(
    base_url: str, api_key: str, query: str, top_k: int | None, timeout_seconds: float
) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
        response = await client.post(
            "/api/v1/documents/ask",
            json={"query": query, "top_k": top_k, "stream": False},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return dict(response.json())


async def search(
    base_url: str, api_key: str, query: str, top_k: int | None, timeout_seconds: float
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
        response = await client.post(
            "/api/v1/documents/search",
            json={"query": query, "top_k": top_k},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return list(response.json()["results"])


async def ingest_text(
    base_url: str,
    api_key: str,
    text: str,
    metadata: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds) as client:
        response = await client.post(
            "/api/v1/documents",
            json={"text": text, "metadata": metadata, "stream": False},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return dict(response.json())
