"""Tests for the BM25 keyword retriever."""

from typing import Any

from retrieval.retriever.bm25_retriever import BM25DocumentRetriever


class FakePayloadSource:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads

    def payloads(self) -> list[dict[str, Any]]:
        return self._payloads


def test_returns_most_relevant_chunk_first() -> None:
    # BM25's classic IDF can degenerate to exactly 0 for a term appearing
    # in exactly half of a 2-document corpus (log((N-n+0.5)/(n+0.5)) ==
    # log(1) == 0), collapsing every score to a tie -- verified directly
    # before writing this test. Four documents avoids that degenerate case.
    source = FakePayloadSource(
        [
            {"id": "a", "text": "The quick brown fox jumps over the lazy dog.", "metadata": {}},
            {
                "id": "b",
                "text": "Ollama serves local language models efficiently.",
                "metadata": {},
            },
            {"id": "c", "text": "Paris is the capital of France.", "metadata": {}},
            {"id": "d", "text": "Water boils at one hundred degrees Celsius.", "metadata": {}},
        ]
    )
    retriever = BM25DocumentRetriever(payload_source=source, top_k=5)

    results = retriever.invoke("local language models")

    assert results[0].id == "b"


def test_respects_top_k() -> None:
    source = FakePayloadSource(
        [
            {"id": str(i), "text": f"document number {i} about testing", "metadata": {}}
            for i in range(10)
        ]
    )
    retriever = BM25DocumentRetriever(payload_source=source, top_k=3)

    results = retriever.invoke("testing")

    assert len(results) == 3


def test_empty_corpus_returns_no_results() -> None:
    retriever = BM25DocumentRetriever(payload_source=FakePayloadSource([]), top_k=5)

    assert retriever.invoke("anything") == []


def test_sets_document_id_and_metadata() -> None:
    source = FakePayloadSource(
        [
            {
                "id": "doc-1:0",
                "text": "Kubernetes orchestrates containers.",
                "metadata": {"document_id": "doc-1"},
            },
        ]
    )
    retriever = BM25DocumentRetriever(payload_source=source, top_k=5)

    results = retriever.invoke("kubernetes containers")

    assert results[0].id == "doc-1:0"
    assert results[0].metadata["chunk_id"] == "doc-1:0"
    assert results[0].metadata["document_id"] == "doc-1"
    assert "score" in results[0].metadata


async def test_async_matches_sync() -> None:
    source = FakePayloadSource(
        [
            {"id": "a", "text": "async and sync should agree", "metadata": {}},
        ]
    )
    retriever = BM25DocumentRetriever(payload_source=source, top_k=5)

    sync_results = retriever.invoke("agree")
    async_results = await retriever.ainvoke("agree")

    assert [d.id for d in sync_results] == [d.id for d in async_results]
