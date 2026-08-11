"""Centralized handling for uncaught exceptions.

Without this, an unhandled exception falls through to Starlette's
default `ServerErrorMiddleware` response: plain text, not JSON, and
never logged through this app's structured logger -- inconsistent with
every other response the API returns, and invisible to log-based
observability.

Must be registered via the `exception_handlers` constructor param on
`FastAPI(...)` (see `backend/main.py`), not `app.add_exception_handler`
after construction: Starlette only wraps `ServerErrorMiddleware` around
a catch-all `Exception` handler if one is present at construction time.
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from backend.models.errors import ErrorResponse

logger = logging.getLogger(__name__)


async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(detail="Internal server error").model_dump(),
    )
