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


def test_app_loads_with_three_tabs_and_no_exception() -> None:
    at = AppTest.from_file(str(_UI_DIR / "app.py")).run()

    assert at.exception == []
    assert [tab.label for tab in at.tabs] == ["💬 Ask", "🔍 Search", "📄 Ingest"]


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
