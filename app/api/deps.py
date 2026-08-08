"""FastAPI dependency providers for services shared across endpoints.

Routed through functions (rather than constructed inline) so tests can
swap in fakes via `app.dependency_overrides`, without a live Ollama daemon
or touching disk.
"""

from functools import lru_cache

from fastapi import Depends

from app.core.config import Settings, get_settings
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
