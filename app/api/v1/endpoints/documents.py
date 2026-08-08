"""Document ingestion and retrieval — the RAG pipeline's HTTP surface.

- `POST /documents`        -> chunk, embed, and store a document's text.
- `POST /documents/search` -> embed a query and return the nearest chunks.

Both require a valid `X-API-Key` header and are subject to a per-key rate
limit; see docs/adr/0003-api-key-auth-and-rate-limiting.md.
"""

from fastapi import APIRouter, Depends

from app.api.deps import enforce_rate_limit, get_ollama_client, get_vector_store
from app.core.config import Settings, get_settings
from app.schemas.documents import (
    IngestRequest,
    IngestResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.ingestion import IngestionService
from app.services.ollama_client import OllamaClient
from app.services.vector_store import VectorStore

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=IngestResponse, summary="Ingest a document")
async def ingest_document(
    body: IngestRequest,
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: VectorStore = Depends(get_vector_store),
    _: None = Depends(enforce_rate_limit),
) -> IngestResponse:
    ingestion = IngestionService(settings, ollama, vector_store)
    result = await ingestion.ingest_document(body.text, body.metadata)
    return IngestResponse(document_id=result.document_id, chunk_count=result.chunk_count)


@router.post("/documents/search", response_model=SearchResponse, summary="Search documents")
async def search_documents(
    body: SearchRequest,
    settings: Settings = Depends(get_settings),
    ollama: OllamaClient = Depends(get_ollama_client),
    vector_store: VectorStore = Depends(get_vector_store),
    _: None = Depends(enforce_rate_limit),
) -> SearchResponse:
    query_vector = await ollama.embed(body.query)
    top_k = body.top_k or settings.SEARCH_TOP_K_DEFAULT
    matches = vector_store.search(query_vector, top_k)

    results = [
        SearchResultItem(
            chunk_id=match.id,
            document_id=str(match.metadata.get("document_id", "")),
            text=match.text,
            score=match.score,
            metadata=match.metadata,
        )
        for match in matches
    ]
    return SearchResponse(results=results)
