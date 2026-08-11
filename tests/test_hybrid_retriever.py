"""Tests for combining vector + BM25 retrieval via RRF."""

from typing import Any

from langchain_core.documents import Document

from retrieval.retriever.hybrid import build_hybrid_retriever, rrf_score, with_rrf_scores
from retrieval.vector_store.port import SearchResult


class FakeEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeHybridStore:
    """Satisfies both `VectorStore` and `PayloadSource`."""

    def __init__(self, results: list[SearchResult], payloads: list[dict[str, Any]]) -> None:
        self._results = results
        self._payloads = payloads

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
        return self._payloads


def test_rrf_score_decreases_with_rank() -> None:
    assert rrf_score(1) > rrf_score(2) > rrf_score(3)


def test_with_rrf_scores_assigns_by_position() -> None:
    docs = [Document(id="a", page_content="a"), Document(id="b", page_content="b")]

    scored = with_rrf_scores(docs)

    assert scored[0].metadata["score"] > scored[1].metadata["score"]
    assert scored[0].metadata["score"] == rrf_score(1)


async def test_hybrid_retriever_combines_and_dedupes() -> None:
    vector_results = [
        SearchResult(
            id="chunk-1",
            score=0.9,
            text="Ollama runs local models.",
            metadata={"document_id": "doc-1"},
        ),
    ]
    payloads = [
        {
            "id": "chunk-1",
            "text": "Ollama runs local models.",
            "metadata": {"document_id": "doc-1"},
        },
        {
            "id": "chunk-2",
            "text": "FastAPI handles HTTP requests.",
            "metadata": {"document_id": "doc-2"},
        },
    ]
    store = FakeHybridStore(vector_results, payloads)

    retriever = build_hybrid_retriever(store, FakeEmbedder(), top_k=5)
    results = await retriever.ainvoke("local models")

    ids = [doc.id for doc in results]
    assert len(ids) == len(set(ids))  # no duplicates -- found-by-both chunk isn't repeated
    assert "chunk-1" in ids
