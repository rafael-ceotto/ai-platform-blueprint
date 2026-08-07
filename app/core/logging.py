"""Structured logging configuration.

Emits JSON logs in production-like environments (easy to ingest into
Loki/ELK/CloudWatch) and human-readable logs for local development.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

_RESERVED_LOG_RECORD_ATTRS = frozenset(logging.LogRecord(
    "", 0, "", 0, "", (), None
).__dict__.keys())


class JSONFormatter(logging.Formatter):
    """Renders each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_ATTRS
        }
        if extras:
            payload["extra"] = extras

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Configure the root logger once, at process startup."""
    settings = get_settings()

    handler = logging.StreamHandler(sys.stdout)
    if settings.LOG_JSON:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(settings.LOG_LEVEL)

    # Quiet down noisy third-party loggers by default.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
