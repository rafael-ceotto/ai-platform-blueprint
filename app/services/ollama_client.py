"""Thin async client around the Ollama HTTP API.

Kept intentionally small: this is the single seam the rest of the app talks
through, so swapping the LLM runtime later (see ADR-0002) means changing
this module, not every call site.
"""

import logging

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self._base_url = str(settings.OLLAMA_BASE_URL).rstrip("/")
        self._model = settings.OLLAMA_MODEL
        self._embedding_model = settings.EMBEDDING_MODEL
        self._timeout = settings.OLLAMA_REQUEST_TIMEOUT_SECONDS

    async def is_reachable(self) -> tuple[bool, str | None]:
        """Best-effort check that the Ollama daemon is up and responding."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/api/version")
                response.raise_for_status()
                return True, None
        except httpx.HTTPError as exc:
            logger.warning("Ollama health check failed: %s", exc)
            return False, str(exc)

    async def generate(self, prompt: str, *, stream: bool = False) -> str:
        """Generate a completion for `prompt` using the configured model."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": prompt, "stream": stream},
            )
            response.raise_for_status()
            return str(response.json()["response"])

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """Return the embedding vector for `text` using the configured embedding model."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": model or self._embedding_model, "prompt": text},
            )
            response.raise_for_status()
            return [float(x) for x in response.json()["embedding"]]
