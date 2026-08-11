"""Orchestrates the answer-generation half of the RAG pipeline via a
LangGraph query-routing graph (classify -> direct-answer or
hybrid-retrieve -> rerank -> generate). See
docs/adr/0006-hybrid-retrieval-and-query-routing.md and
docs/adr/0004-langchain-for-answer-generation.md.
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel

from backend.config.settings import Settings
from llm.ollama.client import OllamaClient
from llm.routing.query_graph import build_query_graph
from retrieval.retriever.hybrid import HybridVectorStore


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

    async def ask(self, query: str, top_k: int | None) -> AskResult:
        result = await self._graph.ainvoke(
            {
                "query": query,
                "top_k": top_k or self._default_top_k,
                "rerank_top_n": self._rerank_top_n,
                "route": "retrieve",
                "documents": [],
                "answer": "",
            }
        )

        sources = [
            AskSource(
                chunk_id=str(doc.metadata["chunk_id"]),
                document_id=str(doc.metadata.get("document_id", "")),
                text=doc.page_content,
                score=float(doc.metadata["score"]),
                metadata=doc.metadata,
            )
            for doc in result["documents"]
        ]
        return AskResult(answer=result["answer"], sources=sources)
