"""Orchestrates the ingest half of the RAG pipeline: chunk -> embed -> store."""

import uuid
from dataclasses import dataclass
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
    ) -> None:
        self._chunk_size = settings.CHUNK_SIZE
        self._chunk_overlap = settings.CHUNK_OVERLAP
        self._ollama = ollama_client
        self._store = vector_store

    async def ingest_document(self, text: str, metadata: dict[str, Any]) -> IngestResult:
        chunks = chunk_text(text, self._chunk_size, self._chunk_overlap)
        document_id = str(uuid.uuid4())
        if not chunks:
            return IngestResult(document_id=document_id, chunk_count=0)

        vectors = [await self._ollama.embed(chunk) for chunk in chunks]
        ids = [f"{document_id}:{i}" for i in range(len(chunks))]
        metadatas = [
            {**metadata, "document_id": document_id, "chunk_index": i} for i in range(len(chunks))
        ]

        self._store.add(ids=ids, vectors=vectors, texts=chunks, metadatas=metadatas)

        return IngestResult(document_id=document_id, chunk_count=len(chunks))
