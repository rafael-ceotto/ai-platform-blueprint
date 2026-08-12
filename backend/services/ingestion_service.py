"""Orchestrates the ingest half of the RAG pipeline: chunk -> embed -> store.

`ingest_document_stream()` is the single source of truth -- it's an ETL
pipeline (chunk -> embed -> store), reported step by step so a client can
show live progress (see docs/adr/0013-etl-progress-and-queryable-ingestion-log.md).
`ingest_document()` is a thin wrapper that drains the same generator for
callers that just want the final result.
"""

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.config.settings import Settings
from ingestion.chunking.chunker import chunk_text
from llm.ollama.client import OllamaClient
from retrieval.vector_store.port import VectorStore


@dataclass
class IngestResult:
    document_id: str
    chunk_count: int


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        ollama_client: OllamaClient,
        vector_store: VectorStore,
        log_vector_store: VectorStore,
    ) -> None:
        self._chunk_size = settings.CHUNK_SIZE
        self._chunk_overlap = settings.CHUNK_OVERLAP
        self._ollama = ollama_client
        self._store = vector_store
        self._log_store = log_vector_store

    async def ingest_document_stream(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_type: str = "text",
        filename: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yields `{"type": "step", "step": "chunking"|"embedding"|"storing"}`
        as ingestion progresses, then one final
        `{"type": "done", "document_id": str, "chunk_count": int}`.

        Also records an entry in the ingestion log (a second FAISS index,
        searchable via the same hybrid retrieval as regular content) once
        the run completes, whether or not any chunks were produced.
        """
        started = time.monotonic()
        started_at = datetime.now(UTC)
        document_id = str(uuid.uuid4())

        yield {"type": "step", "step": "chunking"}
        chunks = chunk_text(text, self._chunk_size, self._chunk_overlap)

        if not chunks:
            await self._log_ingestion(
                document_id,
                source_type,
                filename,
                chunk_count=0,
                duration_ms=self._elapsed_ms(started),
                status="empty",
                started_at=started_at,
            )
            yield {"type": "done", "document_id": document_id, "chunk_count": 0}
            return

        yield {"type": "step", "step": "embedding"}
        vectors = [await self._ollama.embed(chunk) for chunk in chunks]

        yield {"type": "step", "step": "storing"}
        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {**metadata, "document_id": document_id, "chunk_index": i} for i in range(len(chunks))
        ]
        self._store.add(ids=ids, vectors=vectors, texts=chunks, metadatas=metadatas)

        await self._log_ingestion(
            document_id,
            source_type,
            filename,
            chunk_count=len(chunks),
            duration_ms=self._elapsed_ms(started),
            status="success",
            started_at=started_at,
        )
        yield {"type": "done", "document_id": document_id, "chunk_count": len(chunks)}

    async def ingest_document(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_type: str = "text",
        filename: str | None = None,
    ) -> IngestResult:
        result: IngestResult | None = None
        async for event in self.ingest_document_stream(
            text, metadata, source_type=source_type, filename=filename
        ):
            if event["type"] == "done":
                result = IngestResult(
                    document_id=event["document_id"], chunk_count=event["chunk_count"]
                )
        assert result is not None  # ingest_document_stream always yields exactly one "done"
        return result

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    async def _log_ingestion(
        self,
        document_id: str,
        source_type: str,
        filename: str | None,
        *,
        chunk_count: int,
        duration_ms: int,
        status: str,
        started_at: datetime,
    ) -> None:
        source_desc = filename or "raw text"
        text = (
            f"Ingestion log for document {document_id}. Source: {source_type} "
            f"({source_desc}). Started at {started_at.isoformat()}. Completed in "
            f"{duration_ms} ms. Produced {chunk_count} chunk(s). Status: {status}."
        )
        vector = await self._ollama.embed(text)
        self._log_store.add(
            ids=[f"log:{document_id}"],
            vectors=[vector],
            texts=[text],
            metadatas=[
                {
                    "document_id": document_id,
                    "source_type": source_type,
                    "filename": filename,
                    "chunk_count": chunk_count,
                    "duration_ms": duration_ms,
                    "status": status,
                    "started_at": started_at.isoformat(),
                }
            ],
        )
