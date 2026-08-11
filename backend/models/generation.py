"""Schemas for RAG answer generation."""

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=50)
    stream: bool = False


class SourceItem(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    metadata: dict[str, Any]


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
