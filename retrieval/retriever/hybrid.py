"""Combines semantic (vector) and keyword (BM25) retrieval via RRF.

Uses `langchain_classic`'s `EnsembleRetriever` (a maintained package,
unlike the archived `langchain_community`) for the actual fusion. See
docs/adr/0006-hybrid-retrieval-and-query-routing.md.

`EnsembleRetriever` does not expose the fused RRF score on its returned
`Document`s -- it returns whichever sub-retriever's `Document` object it
encountered first, carrying that retriever's own (incomparable) score.
`rrf_score` recomputes a rank-based score from the final fused order
instead, using the same `k=60` convention `EnsembleRetriever` itself
defaults to.
"""

from typing import Protocol, runtime_checkable

from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.documents import Document

from retrieval.retriever.bm25_retriever import BM25DocumentRetriever, PayloadSource
from retrieval.retriever.langchain_retriever import Embedder, VectorStoreRetriever
from retrieval.vector_store.port import VectorStore

_RRF_K = 60


@runtime_checkable
class HybridVectorStore(VectorStore, PayloadSource, Protocol):
    """A `VectorStore` that can also list all payloads -- `FaissVectorStore` satisfies this."""


def build_hybrid_retriever(
    vector_store: HybridVectorStore, embedder: Embedder, top_k: int
) -> EnsembleRetriever:
    """Build an `EnsembleRetriever` combining vector and BM25 search."""
    vector_retriever = VectorStoreRetriever(
        vector_store=vector_store, embedder=embedder, top_k=top_k
    )
    keyword_retriever = BM25DocumentRetriever(payload_source=vector_store, top_k=top_k)
    return EnsembleRetriever(
        retrievers=[vector_retriever, keyword_retriever],
        weights=[0.5, 0.5],
        c=_RRF_K,
    )


def rrf_score(rank: int, k: int = _RRF_K) -> float:
    """Reciprocal Rank Fusion score for a 1-indexed rank position."""
    return 1.0 / (k + rank)


def with_rrf_scores(documents: list[Document]) -> list[Document]:
    """Return copies of `documents` with `metadata["score"]` set to their
    RRF-fused rank score, based on the (already fused/ordered) list
    position -- not whatever single-source score `EnsembleRetriever`
    happened to carry over.
    """
    return [
        doc.model_copy(update={"metadata": {**doc.metadata, "score": rrf_score(rank)}})
        for rank, doc in enumerate(documents, start=1)
    ]
