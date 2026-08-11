"""FAISS-backed `VectorStore` adapter.

See docs/adr/0001-vector-store-faiss-vs-qdrant.md for why FAISS was chosen
for this stage. Vectors are L2-normalized on insert and query and compared
by inner product, which is equivalent to cosine similarity.

The index dimension is inferred from the first batch of vectors added
(not configured), so the store is agnostic to which embedding model is in
use. Ids/text/metadata live in a JSON sidecar next to the index file,
positionally aligned with FAISS's internal vector ordering.
"""

import json
import logging
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from retrieval.vector_store.port import SearchResult

logger = logging.getLogger(__name__)

_INDEX_FILENAME = "index.faiss"
_PAYLOADS_FILENAME = "payloads.json"


class FaissVectorStore:
    def __init__(self, path: str) -> None:
        self._dir = Path(path)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._dir / _INDEX_FILENAME
        self._payloads_path = self._dir / _PAYLOADS_FILENAME

        self._index: Any | None = None
        self._payloads: list[dict[str, Any]] = []  # position -> {id, text, metadata}

        self._load()

    def add(
        self,
        ids: list[str],
        vectors: list[list[float]],
        texts: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        if not (len(ids) == len(vectors) == len(texts) == len(metadatas)):
            raise ValueError("ids, vectors, texts, and metadatas must be the same length")
        if not ids:
            return

        matrix = np.asarray(vectors, dtype=np.float32)
        faiss.normalize_L2(matrix)

        if self._index is None:
            self._index = faiss.IndexFlatIP(matrix.shape[1])
        elif matrix.shape[1] != self._index.d:
            raise ValueError(
                f"embedding dimension {matrix.shape[1]} does not match "
                f"existing index dimension {self._index.d}"
            )

        self._index.add(matrix)
        self._payloads.extend(
            {"id": id_, "text": text, "metadata": metadata}
            for id_, text, metadata in zip(ids, texts, metadatas, strict=True)
        )
        self._save()

    def search(self, vector: list[float], top_k: int) -> list[SearchResult]:
        if self._index is None or self._index.ntotal == 0:
            return []

        query = np.asarray([vector], dtype=np.float32)
        faiss.normalize_L2(query)

        scores, indices = self._index.search(query, min(top_k, self._index.ntotal))

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx == -1:
                continue
            payload = self._payloads[idx]
            results.append(
                SearchResult(
                    id=payload["id"],
                    score=float(score),
                    text=payload["text"],
                    metadata=payload["metadata"],
                )
            )
        return results

    def count(self) -> int:
        return int(self._index.ntotal) if self._index is not None else 0

    def payloads(self) -> list[dict[str, Any]]:
        """Return every stored (id, text, metadata) payload.

        The corpus source for the BM25 keyword retriever
        (`retrieval/retriever/bm25_retriever.py`). Returns a shallow copy
        of the internal list so callers can't add/remove entries out
        from under us; the payload dicts themselves are still shared,
        but callers only ever read them.
        """
        return list(self._payloads)

    def _load(self) -> None:
        if self._index_path.exists() and self._payloads_path.exists():
            self._index = faiss.read_index(str(self._index_path))
            self._payloads = json.loads(self._payloads_path.read_text(encoding="utf-8"))
            logger.info("Loaded FAISS index with %d vectors from %s", self._index.ntotal, self._dir)

    def _save(self) -> None:
        assert self._index is not None
        faiss.write_index(self._index, str(self._index_path))
        self._payloads_path.write_text(json.dumps(self._payloads), encoding="utf-8")
