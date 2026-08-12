"""Tests for the LangGraph query-routing graph, independent of GenerationService."""

from typing import Any

from langchain_core.language_models import FakeListChatModel

from llm.routing.query_graph import NO_CONTEXT_ANSWER, NO_LOG_ANSWER, build_query_graph
from retrieval.vector_store.port import SearchResult


class FakeEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeHybridStore:
    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results

    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        return self._results[:top_k]

    def count(self) -> int:
        return len(self._results)

    def payloads(self) -> list[dict[str, Any]]:
        return [{"id": r.id, "text": r.text, "metadata": r.metadata} for r in self._results]


def _base_state(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "top_k": 5,
        "rerank_top_n": 3,
        "route": "retrieve",
        "documents": [],
        "answer": "",
    }


async def test_direct_route_skips_retrieval() -> None:
    chat_model = FakeListChatModel(responses=["DIRECT", "Hello! How can I help?"])
    graph = build_query_graph(FakeHybridStore([]), FakeHybridStore([]), FakeEmbedder(), chat_model)

    result = await graph.ainvoke(_base_state("hi there"))

    assert result["answer"] == "Hello! How can I help?"
    assert result["documents"] == []


async def test_retrieve_route_with_no_matches_skips_generation() -> None:
    chat_model = FakeListChatModel(responses=["RETRIEVE", "should not be used"])
    graph = build_query_graph(FakeHybridStore([]), FakeHybridStore([]), FakeEmbedder(), chat_model)

    result = await graph.ainvoke(_base_state("what is the meaning of life"))

    assert result["answer"] == NO_CONTEXT_ANSWER
    assert result["documents"] == []


async def test_retrieve_route_with_single_document_skips_rerank_call() -> None:
    # Only one candidate -> the rerank node is a no-op (len <= 1), so the
    # chat model is called exactly twice: classify, then generate.
    chat_model = FakeListChatModel(responses=["RETRIEVE", "Final answer."])
    results = [
        SearchResult(id="a", score=0.9, text="Relevant content.", metadata={"document_id": "d1"})
    ]
    graph = build_query_graph(
        FakeHybridStore(results), FakeHybridStore([]), FakeEmbedder(), chat_model
    )

    result = await graph.ainvoke(_base_state("relevant question"))

    assert result["answer"] == "Final answer."
    assert len(result["documents"]) == 1


async def test_retrieve_route_reranks_multiple_documents() -> None:
    chat_model = FakeListChatModel(responses=["RETRIEVE", "2,1", "Final answer citing context."])
    results = [
        SearchResult(id="a", score=0.9, text="First content.", metadata={"document_id": "d1"}),
        SearchResult(id="b", score=0.8, text="Second content.", metadata={"document_id": "d2"}),
    ]
    graph = build_query_graph(
        FakeHybridStore(results), FakeHybridStore([]), FakeEmbedder(), chat_model
    )

    result = await graph.ainvoke(_base_state("relevant question"))

    assert result["answer"] == "Final answer citing context."
    assert len(result["documents"]) == 2


async def test_rerank_respects_rerank_top_n() -> None:
    chat_model = FakeListChatModel(responses=["RETRIEVE", "3,2,1", "Final answer."])
    results = [
        SearchResult(id="a", score=0.9, text="First.", metadata={}),
        SearchResult(id="b", score=0.8, text="Second.", metadata={}),
        SearchResult(id="c", score=0.7, text="Third.", metadata={}),
    ]
    graph = build_query_graph(
        FakeHybridStore(results), FakeHybridStore([]), FakeEmbedder(), chat_model
    )

    state = _base_state("relevant question")
    state["rerank_top_n"] = 2
    result = await graph.ainvoke(state)

    assert len(result["documents"]) == 2


async def test_log_route_answers_from_log_entries() -> None:
    chat_model = FakeListChatModel(responses=["LOG", "That ingestion produced 3 chunks."])
    log_results = [
        SearchResult(
            id="log:doc-1",
            score=0.9,
            text="Ingestion log for document doc-1. Status: success.",
            metadata={"document_id": "doc-1", "chunk_count": 3, "status": "success"},
        )
    ]
    graph = build_query_graph(
        FakeHybridStore([]), FakeHybridStore(log_results), FakeEmbedder(), chat_model
    )

    result = await graph.ainvoke(_base_state("what happened when I ingested doc-1?"))

    assert result["answer"] == "That ingestion produced 3 chunks."
    assert len(result["documents"]) == 1
    # No rerank step for the log route -- only classify + log_generate are
    # consumed, so if a third response were required this would error.


async def test_log_route_with_no_matching_entries_skips_generation() -> None:
    chat_model = FakeListChatModel(responses=["LOG", "should not be used"])
    graph = build_query_graph(FakeHybridStore([]), FakeHybridStore([]), FakeEmbedder(), chat_model)

    result = await graph.ainvoke(
        _base_state("what happened with a document that was never ingested?")
    )

    assert result["answer"] == NO_LOG_ANSWER
    assert result["documents"] == []
