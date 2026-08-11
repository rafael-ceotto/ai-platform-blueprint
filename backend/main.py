"""FastAPI application entrypoint / app factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import handle_unhandled_exception
from backend.api.v1.router import api_router
from backend.config.settings import get_settings
from observability.logging.setup import configure_logging
from observability.metrics import setup as metrics
from observability.tracing import setup as tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting %s in %s environment", settings.APP_NAME, settings.ENVIRONMENT
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        description="Production-grade blueprint for building AI/LLM platforms.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        exception_handlers={Exception: handle_unhandled_exception},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    tracing.instrument_app(app, settings)
    metrics.instrument_app(app, settings)

    return app


app = create_app()
