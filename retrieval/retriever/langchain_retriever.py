"""LangChain retriever adapter over our own VectorStore + embedding client.

Wraps the existing retrieval building blocks (ADR-0001's `VectorStore`
port, the Ollama embedding client) behind LangChain's `BaseRetriever`
interface so they can be composed into an LCEL chain in
`backend/services/generation_service.py`. LangChain doesn't own
retrieval or embedding here — it consumes them; see
docs/adr/0004-langchain-for-answer-generation.md.
"""

from typing import Protocol, runtime_checkable

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from retrieval.vector_store.port import VectorStore


@runtime_checkable
class Embedder(Protocol):
    """Whatever can embed text — `OllamaClient` today, others later.

    A narrow Protocol (rather than requiring the concrete `OllamaClient`)
    so `VectorStoreRetriever` only depends on the one capability it needs,
    and so pydantic (which `BaseRetriever` is built on) can validate it
    structurally instead of by exact class.
    """

    async def embed(self, text: str) -> list[float]: ...


class VectorStoreRetriever(BaseRetriever):
    """Retrieves the `top_k` nearest chunks to a query from `vector_store`."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: VectorStore
    embedder: Embedder
    top_k: int = 5

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        # The whole stack is async (FastAPI, httpx.AsyncClient in
        # OllamaClient) — only the async path is meaningful here.
        raise NotImplementedError("VectorStoreRetriever is async-only; use .ainvoke()")

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        vector = await self.embedder.embed(query)
        matches = self.vector_store.search(vector, self.top_k)
        return [
            Document(
                page_content=match.text,
                metadata={**match.metadata, "chunk_id": match.id, "score": match.score},
            )
            for match in matches
        ]
