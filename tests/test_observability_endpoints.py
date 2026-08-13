"""API-level tests for the read-only /observability endpoints."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.deps import get_llm_trace_store, get_rate_limiter
from backend.api.rate_limit import InMemoryRateLimiter
from backend.config.settings import Settings, get_settings
from backend.main import create_app
from observability.llm_traces.models import LLMTrace, NodeAggregate, TraceSummary

TEST_API_KEY = "test-key"
AUTH_HEADERS = {"X-API-Key": TEST_API_KEY}

_TRACE = LLMTrace(
    request_id="req-1",
    node="generate",
    model="llama3.1:8b",
    prompt="What is Konsole.ai?",
    completion="A local-first RAG platform.",
    prompt_tokens=12,
    completion_tokens=8,
    latency_ms=123.4,
    cost_usd=0.0,
    created_at="2026-08-13T10:00:00+00:00",
)

_SUMMARY = TraceSummary(
    total_requests=1,
    total_calls=1,
    total_cost_usd=0.0,
    total_prompt_tokens=12,
    total_completion_tokens=8,
    avg_latency_ms=123.4,
    p95_latency_ms=123.4,
    by_node=[NodeAggregate(node="generate", calls=1, total_cost_usd=0.0, avg_latency_ms=123.4)],
)


class FakeLLMTraceStore:
    def record(self, trace: LLMTrace) -> None:
        raise NotImplementedError

    def recent(self, limit: int = 50) -> list[LLMTrace]:
        return [_TRACE][:limit]

    def summary(self) -> TraceSummary:
        return _SUMMARY


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    test_settings = Settings(API_KEYS=[TEST_API_KEY], RATE_LIMIT_REQUESTS=1000)
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_llm_trace_store] = lambda: FakeLLMTraceStore()
    rate_limiter = InMemoryRateLimiter(max_requests=1000, window_seconds=60)
    app.dependency_overrides[get_rate_limiter] = lambda: rate_limiter
    with TestClient(app) as test_client:
        yield test_client


def test_list_traces_returns_recent_calls(client: TestClient) -> None:
    response = client.get("/api/v1/observability/traces", headers=AUTH_HEADERS)

    assert response.status_code == 200
    traces = response.json()["traces"]
    assert len(traces) == 1
    assert traces[0]["request_id"] == "req-1"
    assert traces[0]["node"] == "generate"
    assert traces[0]["prompt_tokens"] == 12


def test_list_traces_respects_limit_query_param(client: TestClient) -> None:
    response = client.get(
        "/api/v1/observability/traces", params={"limit": 0}, headers=AUTH_HEADERS
    )

    assert response.status_code == 422


def test_list_traces_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/observability/traces")
    assert response.status_code == 401


def test_trace_summary_returns_aggregates(client: TestClient) -> None:
    response = client.get("/api/v1/observability/summary", headers=AUTH_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 1
    assert body["total_calls"] == 1
    assert body["by_node"][0]["node"] == "generate"
    assert body["by_node"][0]["calls"] == 1


def test_trace_summary_without_api_key_is_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/observability/summary")
    assert response.status_code == 401
