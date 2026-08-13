"""Aggregates all v1 endpoint routers under a single APIRouter."""

from fastapi import APIRouter

from backend.api.v1.endpoints import documents, health, observability

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(observability.router)
