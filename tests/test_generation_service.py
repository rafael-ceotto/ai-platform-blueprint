"""Unit tests for GenerationService, independent of the HTTP layer."""

from typing import Any

from langchain_core.language_models import FakeListChatModel

from backend.config.settings import Settings
from backend.services.generation_service import GenerationService
from retrieval.vector_store.port import SearchResult, VectorStore

FAKE_ANSWER = "Local SLMs run entirely on your machine."


class FakeOllamaClient:
    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeVectorStore:
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


def _settings() -> Settings:
    return Settings(SEARCH_TOP_K_DEFAULT=5)


async def test_ask_returns_generated_answer_and_sources() -> None:
    results = [
        SearchResult(
            id="doc-1:0",
            score=0.9,
            text="Ollama runs SLMs locally.",
            metadata={"document_id": "doc-1", "chunk_index": 0},
        )
    ]
    vector_store: VectorStore = FakeVectorStore(results)
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        vector_store,
        FakeListChatModel(responses=[FAKE_ANSWER]),
    )

    result = await service.ask("How do SLMs run?", top_k=None)

    assert result.answer == FAKE_ANSWER
    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == "doc-1:0"
    assert result.sources[0].document_id == "doc-1"


async def test_ask_with_no_retrieved_documents_skips_the_llm() -> None:
    vector_store: VectorStore = FakeVectorStore([])
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        vector_store,
        FakeListChatModel(responses=[FAKE_ANSWER]),
    )

    result = await service.ask("Anything?", top_k=None)

    assert result.answer != FAKE_ANSWER
    assert result.sources == []
