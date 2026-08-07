"""Aggregates all v1 endpoint routers under a single APIRouter."""

from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()
api_router.include_router(health.router)
