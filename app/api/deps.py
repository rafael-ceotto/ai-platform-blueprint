"""FastAPI dependency providers for services shared across endpoints.

Routed through functions (rather than constructed inline) so tests can
swap in fakes via `app.dependency_overrides`, without a live Ollama daemon
or touching disk.
"""

from functools import lru_cache

from fastapi import Depends, HTTPException, Security, status

from app.core.config import Settings, get_settings
from app.core.rate_limit import InMemoryRateLimiter
from app.core.security import api_key_header, verify_api_key
from app.services.faiss_store import FaissVectorStore
from app.services.ollama_client import OllamaClient


def get_ollama_client(settings: Settings = Depends(get_settings)) -> OllamaClient:
    return OllamaClient(settings)


@lru_cache
def get_vector_store() -> FaissVectorStore:
    """Return a process-wide singleton FAISS store.

    Cached (rather than constructed per-request) because the FAISS index is
    stateful, in-process data that must persist across requests.
    """
    settings = get_settings()
    return FaissVectorStore(settings.VECTOR_STORE_PATH)


def require_api_key(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> str:
    if not verify_api_key(api_key, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    assert api_key is not None  # narrowed by verify_api_key above
    return api_key


@lru_cache
def get_rate_limiter() -> InMemoryRateLimiter:
    """Return a process-wide singleton rate limiter (see InMemoryRateLimiter)."""
    settings = get_settings()
    return InMemoryRateLimiter(
        max_requests=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
    )


def enforce_rate_limit(
    api_key: str = Depends(require_api_key),
    limiter: InMemoryRateLimiter = Depends(get_rate_limiter),
) -> None:
    if not limiter.allow(api_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(int(limiter.window_seconds))},
        )
