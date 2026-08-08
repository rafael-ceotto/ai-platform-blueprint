"""Port for the vector similarity search backend.

`FaissVectorStore` (`retrieval/vector_store/faiss_store.py`) is the first adapter;
see docs/adr/0001-vector-store-faiss-vs-qdrant.md for why. Callers should
depend on this `Protocol`, not the concrete adapter, so swapping backends
later is a new adapter, not a rewrite of call sites.
"""

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: str
    score: float
    text: str
    metadata: dict[str, Any]


@runtime_checkable
class VectorStore(Protocol):
    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Add vectors with their associated text and metadata."""
        ...

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        """Return the `top_k` nearest neighbors to `vector`, best match first."""
        ...

    def count(self) -> int:
        """Return the total number of vectors currently stored."""
        ...
