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
    APP_NAME: str = "Konsole.ai"
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

    # --- Ingestion log (queryable ETL history) ---
    # See docs/adr/0013-etl-progress-and-queryable-ingestion-log.md
    # A second, independent FaissVectorStore -- same mechanism as the
    # content index above, just a different directory -- so ingestion
    # runs are searchable/askable via the same hybrid retrieval code.
    LOG_VECTOR_STORE_PATH: str = "./data/ingestion_logs"

    # --- LLM call tracing (cost / tokens / latency observability) ---
    # See docs/adr/0015-llm-tracing-and-cost-observability.md
    LLM_TRACE_DB_PATH: str = "./data/llm_traces.db"

    # --- RAG pipeline (chunking / retrieval) ---
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    SEARCH_TOP_K_DEFAULT: int = 5

    # --- Auth / rate limiting ---
    # See docs/adr/0003-api-key-auth-and-rate-limiting.md
    # An empty list fails closed: every request to a protected endpoint is
    # rejected rather than silently allowed. Change before any real deploy.
    API_KEYS: list[str] = Field(default_factory=lambda: ["dev-local-key"])
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: float = 60.0

    # --- Document ingestion (file upload) ---
    # See docs/adr/0005-document-loaders.md
    MAX_UPLOAD_SIZE_BYTES: int = 10_000_000

    # --- Hybrid retrieval / query routing / re-ranking ---
    # See docs/adr/0006-hybrid-retrieval-and-query-routing.md
    # SEARCH_TOP_K_DEFAULT is the initial retrieval breadth (for both
    # /search and /ask); RERANK_TOP_N is how many of those survive the
    # LLM rerank into the /ask generation context.
    RERANK_TOP_N: int = 3

    # --- Observability: tracing (OpenTelemetry -> Jaeger) / metrics (Prometheus) ---
    # See docs/adr/0008-observability-tracing-metrics-dashboards.md and
    # docs/adr/0011-docker-compose-profiles.md.
    # Both default off: instrumenting more than one FastAPI app against the
    # process-global tracer provider / Prometheus registry raises on the
    # second call, and the test suite calls create_app() many times in one
    # process. The jaeger/prometheus/grafana containers are also opt-in
    # (the "observability" Compose profile) -- these two flags are set to
    # "true" alongside that profile so there's something to export/scrape.
    TRACING_ENABLED: bool = False
    METRICS_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "konsole-ai-api"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
