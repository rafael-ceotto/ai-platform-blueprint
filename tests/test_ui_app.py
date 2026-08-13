"""Smoke test for the Streamlit demo UI. See docs/adr/0010-streamlit-demo-ui.md.

Not part of the strict-mypy'd package structure (backend/ingestion/
retrieval/llm/observability) -- ui/ talks to the API only over HTTP, so
this just exercises the Streamlit script runner directly.
"""

import sys
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

_UI_DIR = Path(__file__).resolve().parent.parent / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import api_client  # noqa: E402


def test_app_loads_with_four_tabs_and_no_exception() -> None:
    at = AppTest.from_file(str(_UI_DIR / "app.py")).run()

    assert at.exception == []
    assert [tab.label for tab in at.tabs] == [
        "💬 Ask",
        "🔍 Search",
        "📄 Ingest",
        "📊 Observability",
    ]


def test_search_tab_renders_results_from_a_mocked_api_call() -> None:
    fake_results = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "text": "Hello world.",
            "score": 0.9,
            "metadata": {},
        }
    ]

    with patch.object(api_client, "search", return_value=fake_results) as mock_search:
        at = AppTest.from_file(str(_UI_DIR / "app.py")).run(timeout=10)
        search_tab = at.tabs[1]
        search_tab.text_input(key="search_query").input("hello").run(timeout=10)
        search_tab.button(key="search_button").click().run(timeout=10)

    assert at.exception == []
    mock_search.assert_called_once()
    assert len(at.dataframe) == 1


def test_observability_tab_renders_summary_and_traces_on_refresh() -> None:
    fake_summary = {
        "total_requests": 2,
        "total_calls": 3,
        "total_cost_usd": 0.0,
        "total_prompt_tokens": 40,
        "total_completion_tokens": 20,
        "avg_latency_ms": 150.0,
        "p95_latency_ms": 200.0,
        "by_node": [
            {"node": "generate", "calls": 2, "total_cost_usd": 0.0, "avg_latency_ms": 150.0}
        ],
    }
    fake_traces = [
        {
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
    ]

    with (
        patch.object(api_client, "get_trace_summary", return_value=fake_summary) as mock_summary,
        patch.object(api_client, "get_traces", return_value=fake_traces) as mock_traces,
    ):
        at = AppTest.from_file(str(_UI_DIR / "app.py")).run(timeout=10)
        observability_tab = at.tabs[3]
        observability_tab.button(key="observability_refresh").click().run(timeout=10)

    assert at.exception == []
    mock_summary.assert_called_once()
    mock_traces.assert_called_once()
    assert any(m.value == "2" for m in at.metric)
