"""Unit tests for the SQLite-backed LLMTraceStore."""

from pathlib import Path

from observability.llm_traces.models import LLMTrace
from observability.llm_traces.store import LLMTraceStore


def _trace(**overrides: object) -> LLMTrace:
    defaults: dict[str, object] = {
        "request_id": "req-1",
        "node": "generate",
        "model": "llama3.1:8b",
        "prompt": "What is Konsole.ai?",
        "completion": "A local-first RAG platform.",
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "latency_ms": 123.4,
        "cost_usd": 0.0,
        "created_at": "2026-08-13T10:00:00+00:00",
    }
    defaults.update(overrides)
    return LLMTrace(**defaults)  # type: ignore[arg-type]


def test_record_and_recent_round_trip(tmp_path: Path) -> None:
    store = LLMTraceStore(str(tmp_path / "traces.db"))

    store.record(_trace())

    recent = store.recent()
    assert len(recent) == 1
    assert recent[0].request_id == "req-1"
    assert recent[0].node == "generate"
    assert recent[0].prompt_tokens == 12


def test_recent_returns_newest_first_and_respects_limit(tmp_path: Path) -> None:
    store = LLMTraceStore(str(tmp_path / "traces.db"))
    for i in range(5):
        store.record(_trace(request_id=f"req-{i}"))

    recent = store.recent(limit=2)

    assert [t.request_id for t in recent] == ["req-4", "req-3"]


def test_record_tolerates_missing_token_counts(tmp_path: Path) -> None:
    store = LLMTraceStore(str(tmp_path / "traces.db"))

    store.record(_trace(prompt_tokens=None, completion_tokens=None))

    recent = store.recent()
    assert recent[0].prompt_tokens is None
    assert recent[0].completion_tokens is None


def test_summary_on_empty_store(tmp_path: Path) -> None:
    store = LLMTraceStore(str(tmp_path / "traces.db"))

    summary = store.summary()

    assert summary.total_requests == 0
    assert summary.total_calls == 0
    assert summary.total_cost_usd == 0
    assert summary.p95_latency_ms == 0
    assert summary.by_node == []


def test_summary_aggregates_across_requests_and_nodes(tmp_path: Path) -> None:
    store = LLMTraceStore(str(tmp_path / "traces.db"))
    store.record(_trace(request_id="req-1", node="classify_query", latency_ms=10.0, cost_usd=0.0))
    store.record(_trace(request_id="req-1", node="generate", latency_ms=100.0, cost_usd=0.01))
    store.record(_trace(request_id="req-2", node="generate", latency_ms=200.0, cost_usd=0.02))

    summary = store.summary()

    assert summary.total_requests == 2
    assert summary.total_calls == 3
    assert summary.total_cost_usd == 0.03
    by_node = {n.node: n for n in summary.by_node}
    assert by_node["generate"].calls == 2
    assert by_node["classify_query"].calls == 1


def test_store_persists_across_instances(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    LLMTraceStore(db_path).record(_trace())

    reopened = LLMTraceStore(db_path)

    assert len(reopened.recent()) == 1
