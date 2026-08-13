"""Tests for the Konsole.ai MCP server. See docs/adr/0016-mcp-server-support.md.

Uses the `mcp` SDK's in-process `Client` (connects directly to the
`MCPServer` object, no subprocess/stdio) so these never need a live
`mcp dev` process. HTTP calls are faked by patching `mcp_server.api_client`
functions, mirroring `tests/test_ui_app.py`'s `patch.object(api_client, ...)`
style -- no live API or Ollama needed, matching the rest of the suite's
zero-live-dependency invariant.
"""

from unittest.mock import patch

import pytest
from mcp.client import Client

from mcp_server import api_client
from mcp_server.config import load_config
from mcp_server.server import mcp


async def test_lists_exactly_the_three_expected_tools() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

    by_name = {tool.name: tool for tool in result.tools}
    assert set(by_name) == {"ask", "search", "ingest_text"}
    assert set(by_name["ask"].input_schema["properties"]) == {"query", "top_k"}
    assert set(by_name["search"].input_schema["properties"]) == {"query", "top_k"}
    assert set(by_name["ingest_text"].input_schema["properties"]) == {"text", "metadata"}


async def test_ask_tool_calls_api_client_and_returns_its_result() -> None:
    fake_result = {"answer": "Konsole.ai is a local-first RAG platform.", "sources": []}
    with patch.object(api_client, "ask", return_value=fake_result) as mock_ask:
        async with Client(mcp) as client:
            result = await client.call_tool("ask", {"query": "What is Konsole.ai?"})

    assert not result.is_error
    assert result.structured_content == fake_result
    mock_ask.assert_called_once()
    assert mock_ask.call_args.args[2] == "What is Konsole.ai?"


async def test_search_tool_wraps_api_client_results_in_a_results_key() -> None:
    fake_results = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "text": "hi",
            "score": 0.9,
            "metadata": {},
        }
    ]
    with patch.object(api_client, "search", return_value=fake_results) as mock_search:
        async with Client(mcp) as client:
            result = await client.call_tool("search", {"query": "hello", "top_k": 3})

    assert not result.is_error
    assert result.structured_content == {"results": fake_results}
    mock_search.assert_called_once()
    assert mock_search.call_args.args[2:4] == ("hello", 3)


async def test_ingest_text_tool_calls_api_client_and_returns_its_result() -> None:
    fake_result = {"document_id": "doc-123", "chunk_count": 4}
    with patch.object(api_client, "ingest_text", return_value=fake_result) as mock_ingest:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "ingest_text", {"text": "some content", "metadata": {"source": "test"}}
            )

    assert not result.is_error
    assert result.structured_content == fake_result
    mock_ingest.assert_called_once()
    assert mock_ingest.call_args.args[2:4] == ("some content", {"source": "test"})


async def test_tool_error_surfaces_as_mcp_tool_error_not_a_crash() -> None:
    with patch.object(api_client, "ask", side_effect=api_client.ApiError("500: boom")):
        async with Client(mcp) as client:
            result = await client.call_tool("ask", {"query": "anything"})

    assert result.is_error
    assert "500: boom" in result.content[0].text


def test_load_config_reads_env_vars_and_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KONSOLE_API_BASE_URL", raising=False)
    monkeypatch.delenv("KONSOLE_API_KEY", raising=False)
    monkeypatch.delenv("KONSOLE_API_TIMEOUT_SECONDS", raising=False)
    defaults = load_config()
    assert defaults.api_base_url == "http://localhost:8000"
    assert defaults.api_key == "dev-local-key"
    assert defaults.timeout_seconds == 90.0

    monkeypatch.setenv("KONSOLE_API_BASE_URL", "http://api:9000")
    monkeypatch.setenv("KONSOLE_API_KEY", "secret")
    monkeypatch.setenv("KONSOLE_API_TIMEOUT_SECONDS", "5")
    overridden = load_config()
    assert overridden.api_base_url == "http://api:9000"
    assert overridden.api_key == "secret"
    assert overridden.timeout_seconds == 5.0
