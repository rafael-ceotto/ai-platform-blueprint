"""Orchestrates the answer-generation half of the RAG pipeline via a
LangGraph query-routing graph (classify -> direct-answer or
hybrid-retrieve -> rerank -> generate). See
docs/adr/0006-hybrid-retrieval-and-query-routing.md,
docs/adr/0004-langchain-for-answer-generation.md, and
docs/adr/0007-sse-streaming.md.
"""

from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from typing import Any, cast

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel

from backend.config.settings import Settings
from llm.ollama.client import OllamaClient
from llm.routing.query_graph import GraphState, build_query_graph
from retrieval.retriever.hybrid import HybridVectorStore

_STREAMED_NODES = frozenset({"generate", "direct_answer"})


@dataclass
class AskSource:
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any]


@dataclass
class AskResult:
    answer: str
    sources: list[AskSource]


class GenerationService:
    def __init__(
        self,
        settings: Settings,
        ollama_client: OllamaClient,
        vector_store: HybridVectorStore,
        chat_model: BaseChatModel,
    ) -> None:
        self._default_top_k = settings.SEARCH_TOP_K_DEFAULT
        self._rerank_top_n = settings.RERANK_TOP_N
        self._graph = build_query_graph(vector_store, ollama_client, chat_model)

    def _initial_state(self, query: str, top_k: int | None) -> GraphState:
        return {
            "query": query,
            "top_k": top_k or self._default_top_k,
            "rerank_top_n": self._rerank_top_n,
            "route": "retrieve",
            "documents": [],
            "answer": "",
        }

    def _sources(self, documents: list[Document]) -> list[AskSource]:
        return [
            AskSource(
                chunk_id=str(doc.metadata["chunk_id"]),
                document_id=str(doc.metadata.get("document_id", "")),
                text=doc.page_content,
                score=float(doc.metadata["score"]),
                metadata=doc.metadata,
            )
            for doc in documents
        ]

    async def ask(self, query: str, top_k: int | None) -> AskResult:
        result = await self._graph.ainvoke(self._initial_state(query, top_k))
        return AskResult(answer=result["answer"], sources=self._sources(result["documents"]))

    async def ask_stream(self, query: str, top_k: int | None) -> AsyncIterator[dict[str, Any]]:
        """Yields `{"type": "token", "content": str}` deltas as the answer
        is generated, followed by one final
        `{"type": "done", "answer": str, "sources": [...]}` event.

        Only tokens from the answer-producing nodes (`generate`,
        `direct_answer`) are yielded -- the internal `classify_query` and
        `rerank` LLM calls stream too (LangGraph streams from every node
        that calls a chat model), but their output isn't meant for the
        client and is filtered out by node name.

        The `no_context_answer` node (nothing retrieved) sets a fixed
        answer without calling the chat model at all, so it produces no
        token events -- the final `done` event always carries the full
        `answer` text too, not just `sources`, so that path isn't silent.
        """
        documents: list[Document] = []
        answer = ""

        # The installed langgraph type stubs don't model the tuple shape
        # `astream` actually yields for multi-mode (v1, default) streaming
        # -- verified directly against the real runtime behavior before
        # writing this, so the cast reflects what's actually returned.
        stream = cast(
            "AsyncIterator[tuple[str, Any]]",
            self._graph.astream(
                self._initial_state(query, top_k), stream_mode=["messages", "values"]
            ),
        )
        async for stream_mode, payload in stream:
            if stream_mode == "values":
                documents = payload["documents"]
                answer = payload["answer"]
                continue

            chunk, metadata = payload
            if metadata.get("langgraph_node") in _STREAMED_NODES and chunk.content:
                yield {"type": "token", "content": chunk.content}

        sources = [asdict(source) for source in self._sources(documents)]
        yield {"type": "done", "answer": answer, "sources": sources}
