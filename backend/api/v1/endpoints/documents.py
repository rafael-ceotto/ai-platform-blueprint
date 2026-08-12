"""Document ingestion and retrieval — the RAG pipeline's HTTP surface.

- `POST /documents`        -> chunk, embed, and store a document's text.
- `POST /documents/upload` -> same, from an uploaded PDF/Markdown/TXT/HTML
  file (see docs/adr/0005-document-loaders.md).
- `POST /documents/search` -> embed a query and return the nearest chunks.
- `POST /documents/ask`    -> retrieve context and have the SLM generate
  an answer from it (see docs/adr/0004-langchain-for-answer-generation.md).

Both ingest endpoints and `/documents/ask` accept `"stream": true` (a
form field for `/documents/upload`) to get step-by-step progress / the
answer as Server-Sent Events instead of a single JSON response (see
docs/adr/0007-sse-streaming.md and
docs/adr/0013-etl-progress-and-queryable-ingestion-log.md). Every
completed ingestion is also logged to a separate, searchable index --
ask about it via `/documents/ask` (e.g. "what happened when I uploaded
doc <id>").

All four require a valid `X-API-Key` header and are subject to a
per-key rate limit; see docs/adr/0003-api-key-auth-and-rate-limiting.md.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from langchain_core.language_models import BaseChatModel

from backend.api.deps import (
    enforce_rate_limit,
    get_chat_model,
    get_log_vector_store,
    get_ollama_client,
    get_vector_store,
)
from backend.api.sse import sse_event_stream
from backend.config.settings import Settings, get_settings
from backend.models.documents import (
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from backend.models.generation import AskRequest, AskResponse, SourceItem
from backend.services.generation_service import GenerationService
from backend.services.ingestion_service import IngestionService
from ingestion.loaders.dispatch import UnsupportedFileTypeError, load_document
from llm.ollama.client import OllamaClient
from retrieval.retriever.hybrid import HybridVectorStore, build_hybrid_retriever, with_rrf_scores
from retrieval.vector_store.port import VectorStore

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=IngestResponse, summary="Ingest a document")
async def ingest_document(
    body: IngestRequest,
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: VectorStore = Depends(get_vector_store),
    log_vector_store: VectorStore = Depends(get_log_vector_store),
    _: None = Depends(enforce_rate_limit),
) -> IngestResponse | StreamingResponse:
    ingestion = IngestionService(settings, ollama, vector_store, log_vector_store)

    if body.stream:
        return StreamingResponse(
            sse_event_stream(ingestion.ingest_document_stream(body.text, body.metadata)),
            media_type="text/event-stream",
        )

    result = await ingestion.ingest_document(body.text, body.metadata)
    return IngestResponse(document_id=result.document_id, chunk_count=result.chunk_count)


@router.post("/documents/upload", response_model=IngestResponse, summary="Upload a document file")
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Form(default="{}"),
    stream: bool = Form(default=False),
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: VectorStore = Depends(get_vector_store),
    log_vector_store: VectorStore = Depends(get_log_vector_store),
    _: None = Depends(enforce_rate_limit),
) -> IngestResponse | StreamingResponse:
    try:
        parsed_metadata = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="metadata must be valid JSON",
        ) from exc

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_BYTES} byte upload limit",
        )

    filename = file.filename or ""
    ingestion = IngestionService(settings, ollama, vector_store, log_vector_store)

    if stream:

        async def _stream() -> AsyncIterator[dict[str, Any]]:
            yield {"type": "step", "step": "loading"}
            try:
                text = load_document(filename, content)
            except UnsupportedFileTypeError as exc:
                yield {"type": "error", "detail": str(exc)}
                return
            async for event in ingestion.ingest_document_stream(
                text, parsed_metadata, source_type="upload", filename=filename
            ):
                yield event

        return StreamingResponse(sse_event_stream(_stream()), media_type="text/event-stream")

    try:
        text = load_document(filename, content)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    result = await ingestion.ingest_document(
        text, parsed_metadata, source_type="upload", filename=filename
    )
    return IngestResponse(document_id=result.document_id, chunk_count=result.chunk_count)


@router.post("/documents/search", response_model=SearchResponse, summary="Search documents")
async def search_documents(
    body: SearchRequest,
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: HybridVectorStore = Depends(get_vector_store),
    _: None = Depends(enforce_rate_limit),
) -> SearchResponse:
    top_k = body.top_k or settings.SEARCH_TOP_K_DEFAULT
    retriever = build_hybrid_retriever(vector_store, ollama, top_k)
    documents = with_rrf_scores(await retriever.ainvoke(body.query))

    results = [
        SearchResultItem(
            chunk_id=str(doc.metadata["chunk_id"]),
            document_id=str(doc.metadata.get("document_id", "")),
            text=doc.page_content,
            score=float(doc.metadata["score"]),
            metadata=doc.metadata,
        )
        for doc in documents
    ]
    return SearchResponse(results=results)


@router.post("/documents/ask", response_model=AskResponse, summary="Ask a question")
async def ask_documents(
    body: AskRequest,
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: HybridVectorStore = Depends(get_vector_store),
    log_vector_store: HybridVectorStore = Depends(get_log_vector_store),
    chat_model: BaseChatModel = Depends(get_chat_model),
    _: None = Depends(enforce_rate_limit),
) -> AskResponse | StreamingResponse:
    generation = GenerationService(settings, ollama, vector_store, log_vector_store, chat_model)

    if body.stream:
        return StreamingResponse(
            sse_event_stream(generation.ask_stream(body.query, body.top_k)),
            media_type="text/event-stream",
        )

    result = await generation.ask(body.query, body.top_k)

    sources = [
        SourceItem(
            chunk_id=source.chunk_id,
            document_id=source.document_id,
            text=source.text,
            score=source.score,
            metadata=source.metadata,
        )
        for source in result.sources
    ]
    return AskResponse(answer=result.answer, sources=sources)
