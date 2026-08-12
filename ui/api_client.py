"""Thin HTTP client for the AI Platform Blueprint API, used by ui/app.py.

Kept separate from app.py so the request/response handling can be
mocked in tests without a live API. See docs/adr/0010-streamlit-demo-ui.md.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx2


class ApiError(RuntimeError):
    """Raised when the API returns a non-2xx response."""


@dataclass
class AskEvent:
    """One step of a streamed /documents/ask response."""

    type: str  # "token" | "done" | "error"
    content: str = ""
    answer: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _raise_for_status(response: httpx2.Response) -> None:
    if response.is_error:
        raise ApiError(f"{response.status_code}: {response.text}")


def ingest_text(base_url: str, api_key: str, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    with httpx2.Client(base_url=base_url, timeout=60.0) as client:
        response = client.post(
            "/api/v1/documents",
            json={"text": text, "metadata": metadata},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return dict(response.json())


def upload_file(
    base_url: str, api_key: str, filename: str, content: bytes, metadata: dict[str, Any]
) -> dict[str, Any]:
    with httpx2.Client(base_url=base_url, timeout=60.0) as client:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, content)},
            data={"metadata": json.dumps(metadata)},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return dict(response.json())


def search(base_url: str, api_key: str, query: str, top_k: int | None) -> list[dict[str, Any]]:
    with httpx2.Client(base_url=base_url, timeout=30.0) as client:
        response = client.post(
            "/api/v1/documents/search",
            json={"query": query, "top_k": top_k},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return list(response.json()["results"])


def ask_stream(base_url: str, api_key: str, query: str, top_k: int | None) -> Iterator[AskEvent]:
    """Yields AskEvent("token", content=...) as they arrive, then one
    final AskEvent("done", answer=..., sources=...) or
    AskEvent("error", detail=...)."""
    with (
        httpx2.Client(base_url=base_url, timeout=120.0) as client,
        client.sse(
            "/api/v1/documents/ask",
            method="POST",
            json={"query": query, "top_k": top_k, "stream": True},
            headers=_headers(api_key),
        ) as source,
    ):
        for event in source:
            payload = json.loads(event.data)
            if event.event == "token":
                yield AskEvent(type="token", content=payload["content"])
            elif event.event == "done":
                yield AskEvent(type="done", answer=payload["answer"], sources=payload["sources"])
            elif event.event == "error":
                yield AskEvent(type="error", detail=payload["detail"])
