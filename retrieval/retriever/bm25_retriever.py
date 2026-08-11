"""LangChain retriever backed by BM25 keyword search.

Rebuilds a `rank_bm25.BM25Okapi` index from `payload_source.payloads()`
on every call rather than maintaining a second, separately-persisted
keyword index -- avoids any risk of the vector and keyword indexes
drifting out of sync, and rebuilding is fast enough at this project's
MVP corpus scale. See docs/adr/0006-hybrid-retrieval-and-query-routing.md.

Unlike `VectorStoreRetriever` (async-only, since embedding needs an
HTTP round-trip), this is pure in-memory computation with no I/O, so the
sync path is the "real" implementation and async just delegates to it.
"""

from typing import Any, Protocol, runtime_checkable

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from rank_bm25 import BM25Okapi


@runtime_checkable
class PayloadSource(Protocol):
    """Whatever can list all stored chunks -- `FaissVectorStore` today."""

    def payloads(self) -> list[dict[str, Any]]: ...


class BM25DocumentRetriever(BaseRetriever):
    """Retrieves the `top_k` chunks with the highest BM25 score for a query."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    payload_source: PayloadSource
    top_k: int = 5

    def _search(self, query: str) -> list[Document]:
        payloads = self.payload_source.payloads()
        if not payloads:
            return []

        tokenized_corpus = [str(payload["text"]).lower().split() for payload in payloads]
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query.lower().split())

        ranked = sorted(range(len(payloads)), key=lambda i: scores[i], reverse=True)
        return [
            Document(
                id=str(payloads[i]["id"]),
                page_content=str(payloads[i]["text"]),
                metadata={
                    **payloads[i]["metadata"],
                    "chunk_id": payloads[i]["id"],
                    "score": float(scores[i]),
                },
            )
            for i in ranked[: self.top_k]
        ]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self._search(query)

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self._search(query)
