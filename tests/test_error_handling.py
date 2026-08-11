"""Tests for the global unhandled-exception handler.

Uses a dedicated TestClient with `raise_server_exceptions=False` --
Starlette's TestClient re-raises server exceptions into the test by
default, bypassing the response entirely, which would defeat the point
of testing the handler.
"""

from typing import Any

from fastapi.testclient import TestClient

from backend.api.deps import get_ollama_client, get_vector_store
from backend.main import create_app
from retrieval.vector_store.port import SearchResult


class ExplodingOllamaClient:
    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        raise RuntimeError("a sensitive internal detail that must not leak")


class EmptyVectorStore:
    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        raise NotImplementedError

    def count(self) -> int:
        return 0


def test_unhandled_exception_returns_safe_json_500() -> None:
    app = create_app()
    app.dependency_overrides[get_ollama_client] = lambda: ExplodingOllamaClient()
    app.dependency_overrides[get_vector_store] = lambda: EmptyVectorStore()

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/documents/search",
            json={"query": "test"},
            headers={"X-API-Key": "dev-local-key"},
        )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Internal server error"}
    assert "sensitive internal detail" not in response.text
