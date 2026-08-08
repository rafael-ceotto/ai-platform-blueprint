"""Centralized application settings, loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    Values are resolved in this order (highest priority first):
    process environment -> `.env` file -> field defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "AI Platform Blueprint"
    ENVIRONMENT: Literal["local", "development", "staging", "production"] = "local"
    DEBUG: bool = False
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = True

    # --- API ---
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # --- LLM runtime (Ollama) ---
    # See docs/adr/0002-llm-runtime-ollama-vs-external-apis.md
    OLLAMA_BASE_URL: AnyHttpUrl = Field(default="http://localhost:11434")  # type: ignore[assignment]
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_REQUEST_TIMEOUT_SECONDS: float = 60.0

    # --- Vector store (FAISS) ---
    # See docs/adr/0001-vector-store-faiss-vs-qdrant.md
    VECTOR_STORE_PATH: str = "./data/vector_store"
    EMBEDDING_MODEL: str = "nomic-embed-text"

    # --- RAG pipeline (chunking / retrieval) ---
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    SEARCH_TOP_K_DEFAULT: int = 5

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
