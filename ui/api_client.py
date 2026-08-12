"""Thin HTTP client for the Konsole.ai API, used by ui/app.py.

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


@dataclass
class IngestEvent:
    """One step of a streamed /documents or /documents/upload response."""

    type: str  # "step" | "done" | "error"
    step: str = ""
    document_id: str = ""
    chunk_count: int = 0
    detail: str = ""


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def _raise_for_status(response: httpx2.Response) -> None:
    if response.is_error:
        raise ApiError(f"{response.status_code}: {response.text}")


def search(base_url: str, api_key: str, query: str, top_k: int | None) -> list[dict[str, Any]]:
    with httpx2.Client(base_url=base_url, timeout=30.0) as client:
        response = client.post(
            "/api/v1/documents/search",
            json={"query": query, "top_k": top_k},
            headers=_headers(api_key),
        )
        _raise_for_status(response)
        return list(response.json()["results"])


def ingest_text_stream(
    base_url: str, api_key: str, text: str, metadata: dict[str, Any]
) -> Iterator[IngestEvent]:
    """Yields IngestEvent("step", step=...) as ingestion progresses, then
    one final IngestEvent("done", document_id=..., chunk_count=...) or
    IngestEvent("error", detail=...)."""
    with (
        httpx2.Client(base_url=base_url, timeout=120.0) as client,
        client.sse(
            "/api/v1/documents",
            method="POST",
            json={"text": text, "metadata": metadata, "stream": True},
            headers=_headers(api_key),
        ) as source,
    ):
        yield from _parse_ingest_events(source)


def upload_file_stream(
    base_url: str, api_key: str, filename: str, content: bytes, metadata: dict[str, Any]
) -> Iterator[IngestEvent]:
    """Same shape as `ingest_text_stream`, for an uploaded file."""
    with (
        httpx2.Client(base_url=base_url, timeout=120.0) as client,
        client.sse(
            "/api/v1/documents/upload",
            method="POST",
            files={"file": (filename, content)},
            data={"metadata": json.dumps(metadata), "stream": "true"},
            headers=_headers(api_key),
        ) as source,
    ):
        yield from _parse_ingest_events(source)


def _parse_ingest_events(source: Any) -> Iterator[IngestEvent]:
    for event in source:
        payload = json.loads(event.data)
        if event.event == "step":
            yield IngestEvent(type="step", step=payload["step"])
        elif event.event == "done":
            yield IngestEvent(
                type="done",
                document_id=payload["document_id"],
                chunk_count=payload["chunk_count"],
            )
        elif event.event == "error":
            yield IngestEvent(type="error", detail=payload["detail"])


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
