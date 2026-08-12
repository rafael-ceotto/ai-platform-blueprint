"""Unit tests for GenerationService, independent of the HTTP layer."""

from typing import Any

from langchain_core.language_models import FakeListChatModel

from backend.config.settings import Settings
from backend.services.generation_service import GenerationService
from llm.routing.query_graph import NO_CONTEXT_ANSWER
from retrieval.vector_store.port import SearchResult

FAKE_ANSWER = "Local SLMs run entirely on your machine."


class FakeOllamaClient:
    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        return [1.0, 0.0, 0.0]


class FakeHybridStore:
    """Satisfies both `VectorStore` and `PayloadSource` (`HybridVectorStore`)."""

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


def _settings() -> Settings:
    return Settings(SEARCH_TOP_K_DEFAULT=5, RERANK_TOP_N=3)


async def test_ask_returns_generated_answer_and_sources() -> None:
    results = [
        SearchResult(
            id="doc-1:0",
            score=0.9,
            text="Ollama runs SLMs locally.",
            metadata={"document_id": "doc-1", "chunk_index": 0},
        )
    ]
    store = FakeHybridStore(results)
    # A single retrieved document -> rerank is a no-op (len <= 1), so the
    # chat model is called exactly twice: classify, then generate.
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["RETRIEVE", FAKE_ANSWER]),
    )

    result = await service.ask("How do SLMs run?", top_k=None)

    assert result.answer == FAKE_ANSWER
    assert len(result.sources) == 1
    assert result.sources[0].chunk_id == "doc-1:0"
    assert result.sources[0].document_id == "doc-1"


async def test_ask_with_no_retrieved_documents_skips_the_llm() -> None:
    store = FakeHybridStore([])
    # Retrieval finds nothing -> routed straight to the fixed no-context
    # answer, no generation call. Only "RETRIEVE" (classify) is consumed.
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["RETRIEVE", FAKE_ANSWER]),
    )

    result = await service.ask("Anything?", top_k=None)

    assert result.answer == NO_CONTEXT_ANSWER
    assert result.sources == []


async def test_ask_routes_greeting_to_direct_answer_without_retrieval() -> None:
    store = FakeHybridStore(
        [SearchResult(id="a", score=0.9, text="Unrelated content.", metadata={})]
    )
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["DIRECT", "Hello! How can I help?"]),
    )

    result = await service.ask("hi there", top_k=None)

    assert result.answer == "Hello! How can I help?"
    assert result.sources == []


async def test_ask_reranks_multiple_candidates_before_generating() -> None:
    results = [
        SearchResult(id="a", score=0.9, text="First candidate.", metadata={"document_id": "d1"}),
        SearchResult(id="b", score=0.8, text="Second candidate.", metadata={"document_id": "d2"}),
    ]
    store = FakeHybridStore(results)
    # Two documents -> rerank actually calls the model: classify, rerank,
    # generate (three calls, in that order).
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["RETRIEVE", "2,1", FAKE_ANSWER]),
    )

    result = await service.ask("relevant question", top_k=None)

    assert result.answer == FAKE_ANSWER
    assert len(result.sources) == 2


async def test_ask_stream_yields_tokens_only_from_generate_node() -> None:
    results = [
        SearchResult(
            id="doc-1:0",
            score=0.9,
            text="Ollama runs SLMs locally.",
            metadata={"document_id": "doc-1", "chunk_index": 0},
        )
    ]
    store = FakeHybridStore(results)
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["RETRIEVE", FAKE_ANSWER]),
    )

    events = [event async for event in service.ask_stream("How do SLMs run?", top_k=None)]

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]
    streamed_answer = "".join(e["content"] for e in token_events)

    assert len(done_events) == 1
    assert streamed_answer == FAKE_ANSWER
    # The classify call's own streamed tokens ("RETRIEVE") must never
    # leak into the client-facing token events.
    assert "RETRIEVE" not in streamed_answer
    assert done_events[0]["answer"] == FAKE_ANSWER
    assert done_events[0]["sources"][0]["chunk_id"] == "doc-1:0"


async def test_ask_stream_direct_answer_path_streams_tokens_too() -> None:
    store = FakeHybridStore([])
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["DIRECT", "Hi there!"]),
    )

    events = [event async for event in service.ask_stream("hi", top_k=None)]

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]

    assert "".join(e["content"] for e in token_events) == "Hi there!"
    assert done_events[0]["answer"] == "Hi there!"
    assert done_events[0]["sources"] == []


async def test_ask_stream_with_no_documents_has_no_tokens_but_final_answer() -> None:
    store = FakeHybridStore([])
    service = GenerationService(
        _settings(),
        FakeOllamaClient(),
        store,
        FakeHybridStore([]),
        FakeListChatModel(responses=["RETRIEVE", FAKE_ANSWER]),
    )

    events = [event async for event in service.ask_stream("anything", top_k=None)]

    token_events = [e for e in events if e["type"] == "token"]
    done_events = [e for e in events if e["type"] == "done"]

    # no_context_answer never calls the chat model, so there's nothing to
    # stream token-by-token -- the fixed answer only ever appears in the
    # final "done" event.
    assert token_events == []
    assert done_events[0]["answer"] == NO_CONTEXT_ANSWER
    assert done_events[0]["sources"] == []
