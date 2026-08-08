"""Orchestrates the answer-generation half of the RAG pipeline.

Retrieves via `VectorStoreRetriever`, then runs an LCEL chain
(`RAG_PROMPT | chat_model | StrOutputParser()`) over the retrieved
context. See docs/adr/0004-langchain-for-answer-generation.md.
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from backend.config.settings import Settings
from llm.ollama.client import OllamaClient
from llm.prompts.rag_prompt import RAG_PROMPT
from retrieval.retriever.langchain_retriever import VectorStoreRetriever
from retrieval.vector_store.port import VectorStore

_NO_CONTEXT_ANSWER = "I don't have enough information to answer that."


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
        vector_store: VectorStore,
        chat_model: BaseChatModel,
    ) -> None:
        self._default_top_k = settings.SEARCH_TOP_K_DEFAULT
        self._ollama = ollama_client
        self._vector_store = vector_store
        self._chat_model = chat_model

    async def ask(self, query: str, top_k: int | None) -> AskResult:
        retriever = VectorStoreRetriever(
            vector_store=self._vector_store,
            embedder=self._ollama,
            top_k=top_k or self._default_top_k,
        )
        documents = await retriever.ainvoke(query)

        if not documents:
            return AskResult(answer=_NO_CONTEXT_ANSWER, sources=[])

        context = "\n\n".join(f"[{i + 1}] {doc.page_content}" for i, doc in enumerate(documents))
        chain = RAG_PROMPT | self._chat_model | StrOutputParser()
        answer = await chain.ainvoke({"context": context, "question": query})

        sources = [
            AskSource(
                chunk_id=str(doc.metadata["chunk_id"]),
                document_id=str(doc.metadata.get("document_id", "")),
                text=doc.page_content,
                score=float(doc.metadata["score"]),
                metadata=doc.metadata,
            )
            for doc in documents
        ]
        return AskResult(answer=answer, sources=sources)
