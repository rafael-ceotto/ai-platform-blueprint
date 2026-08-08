"""API-level tests for the /documents ingestion and search endpoints.

Uses fakes for the Ollama client and vector store (via
`app.dependency_overrides`) so these tests need neither a live Ollama
daemon nor disk I/O. The real FAISS adapter is covered separately in
tests/test_faiss_store.py. Auth and rate limiting are exercised against
the real `require_api_key`/`enforce_rate_limit` dependencies (only their
inputs — settings and the rate limiter instance — are overridden), since
those are the thing under test here.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import FakeListChatModel

from backend.api.deps import (
    get_chat_model,
    get_ollama_client,
    get_rate_limiter,
    get_vector_store,
)
from backend.api.rate_limit import InMemoryRateLimiter
from backend.config.settings import Settings, get_settings
from backend.main import create_app
from retrieval.vector_store.port import SearchResult, VectorStore

FAKE_ANSWER = "The retrieved context says so."

TEST_API_KEY = "test-key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}


class FakeOllamaClient:
    """Deterministic bag-of-words embedding, no network calls."""

    _DIM = 16

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        vector = [0.0] * self._DIM
        for word in text.lower().split():
            vector[hash(word) % self._DIM] += 1.0
        return vector


class FakeVectorStore:
    """In-memory brute-force VectorStore, structurally matching the port."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._texts: list[str] = []
        self._metadatas: list[dict[str, Any]] = []

    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._ids.extend(ids)
        self._vectors.extend(vectors)
        self._texts.extend(texts)
        self._metadatas.extend(metadatas)

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        def score(other: list[float]) -> float:
            return sum(a * b for a, b in zip(vector, other, strict=True))

        ranked = sorted(range(len(self._ids)), key=lambda i: score(self._vectors[i]), reverse=True)
        return [
            SearchResult(
                id=self._ids[i],
                score=score(self._vectors[i]),
                text=self._texts[i],
                metadata=self._metadatas[i],
            )
            for i in ranked[:top_k]
        ]

    def count(self) -> int:
        return len(self._ids)


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    fake_store: VectorStore = FakeVectorStore()
    test_settings = Settings(API_KEYS=[TEST_API_KEY], RATE_LIMIT_REQUESTS=1000)
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_vector_store] = lambda: fake_store
    app.dependency_overrides[get_settings] = lambda: test_settings
    # get_rate_limiter is a process-wide @lru_cache singleton in the app;
    # overriding it replaces the *provider*, which FastAPI calls fresh on
    # every request unless the override itself returns the same instance
    # each time — so build it once here and close over it, rather than
    # constructing a new (always-empty) limiter inside the lambda.
    rate_limiter = InMemoryRateLimiter(max_requests=1000, window_seconds=60)
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    app.dependency_overrides[get_chat_model] = lambda: FakeListChatModel(
        responses=[FAKE_ANSWER]
    )
    with TestClient(app) as test_client:
        yield test_client


def test_ingest_document_returns_chunk_count(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        json={"text": "Hello world, this is a test."},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chunk_count"] >= 1
    assert body["document_id"]


def test_ingest_and_search_round_trip(client: TestClient) -> None:
    ingest_response = client.post(
        "/api/v1/documents",
        json={"text": "Ollama serves local LLMs.", "metadata": {"source": "test"}},
        headers=AUTH_HEADERS,
    )
    document_id = ingest_response.json()["document_id"]

    search_response = client.post(
        "/api/v1/documents/search",
        json={"query": "Ollama serves local LLMs.", "top_k": 3},
        headers=AUTH_HEADERS,
    )

    assert search_response.status_code == 200
    results = search_response.json()["results"]
    assert len(results) >= 1
    assert results[0]["document_id"] == document_id
    assert results[0]["metadata"]["source"] == "test"


def test_ingest_rejects_empty_text(client: TestClient) -> None:
    response = client.post("/api/v1/documents", json={"text": ""}, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_search_rejects_empty_query(client: TestClient) -> None:
    response = client.post("/api/v1/documents/search", json={"query": ""}, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_search_top_k_out_of_range_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/search",
        json={"query": "test", "top_k": 0},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


def test_ingest_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/documents", json={"text": "Hello world."})
    assert response.status_code == 401


def test_ingest_with_invalid_api_key_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        json={"text": "Hello world."},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_search_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/documents/search", json={"query": "test"})
    assert response.status_code == 401


def test_rate_limit_exceeded_returns_429() -> None:
    app = create_app()
    fake_store: VectorStore = FakeVectorStore()
    test_settings = Settings(API_KEYS=[TEST_API_KEY], RATE_LIMIT_REQUESTS=1)
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_vector_store] = lambda: fake_store
    app.dependency_overrides[get_settings] = lambda: test_settings
    rate_limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter

    with TestClient(app) as test_client:
        first = test_client.post(
            "/api/v1/documents", json={"text": "one."}, headers=AUTH_HEADERS
        )
        second = test_client.post(
            "/api/v1/documents", json={"text": "two."}, headers=AUTH_HEADERS
        )

    assert first.status_code == 200
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_ask_generates_answer_from_retrieved_context(client: TestClient) -> None:
    client.post(
        "/api/v1/documents",
        json={"text": "Ollama serves local LLMs.", "metadata": {"source": "test"}},
        headers=AUTH_HEADERS,
    )

    response = client.post(
        "/api/v1/documents/ask",
        json={"query": "Ollama serves local LLMs."},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == FAKE_ANSWER
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["text"]


def test_ask_with_no_matching_documents_skips_generation() -> None:
    app = create_app()
    fake_store: VectorStore = FakeVectorStore()
    test_settings = Settings(API_KEYS=[TEST_API_KEY], RATE_LIMIT_REQUESTS=1000)
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_vector_store] = lambda: fake_store
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter(
        max_requests=1000, window_seconds=60
    )
    app.dependency_overrides[get_chat_model] = lambda: FakeListChatModel(
        responses=[FAKE_ANSWER]
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/documents/ask",
            json={"query": "anything"},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] != FAKE_ANSWER
    assert body["sources"] == []


def test_ask_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/documents/ask", json={"query": "test"})
    assert response.status_code == 401


def test_ask_rejects_empty_query(client: TestClient) -> None:
    response = client.post("/api/v1/documents/ask", json={"query": ""}, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_upload_txt_file_ingests_it(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"Uploaded via multipart.", "text/plain")},
        data={"metadata": '{"source": "upload-test"}'},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["chunk_count"] >= 1
    assert body["document_id"]


def test_upload_html_file_is_extracted_and_ingested(client: TestClient) -> None:
    html = b"<html><body><p>Extracted HTML content.</p></body></html>"
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("page.html", html, "text/html")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["chunk_count"] >= 1


def test_upload_unsupported_extension_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("archive.zip", b"whatever", "application/zip")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


def test_upload_invalid_metadata_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"Hello.", "text/plain")},
        data={"metadata": "not-json"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


def test_upload_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"Hello.", "text/plain")},
    )
    assert response.status_code == 401


def test_upload_over_size_limit_is_rejected() -> None:
    app = create_app()
    fake_store: VectorStore = FakeVectorStore()
    test_settings = Settings(
        API_KEYS=[TEST_API_KEY], RATE_LIMIT_REQUESTS=1000, MAX_UPLOAD_SIZE_BYTES=10
    )
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_vector_store] = lambda: fake_store
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter(
        max_requests=1000, window_seconds=60
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.txt", b"This is longer than ten bytes.", "text/plain")},
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 413
