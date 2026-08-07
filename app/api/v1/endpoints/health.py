"""Liveness and readiness endpoints.

- `/health`  -> liveness: is the process up? Always cheap, no I/O.
- `/health/ready` -> readiness: are downstream dependencies (e.g. Ollama)
  reachable? Used by orchestrators/load balancers to gate traffic.
"""

from typing import Literal

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import DependencyStatus, HealthResponse, ReadinessResponse
from app.services.ollama_client import OllamaClient

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        app_name=settings.APP_NAME,
        version="0.1.0",
        environment=settings.ENVIRONMENT,
    )


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(settings: Settings = Depends(get_settings)) -> ReadinessResponse:
    ollama = OllamaClient(settings)
    ollama_ok, ollama_detail = await ollama.is_reachable()

    dependencies = [
        DependencyStatus(name="ollama", healthy=ollama_ok, detail=ollama_detail),
    ]
    overall: Literal["ready", "not_ready"] = (
        "ready" if all(dep.healthy for dep in dependencies) else "not_ready"
    )

    return ReadinessResponse(status=overall, dependencies=dependencies)
