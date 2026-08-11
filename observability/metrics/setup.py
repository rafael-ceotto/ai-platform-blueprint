"""Prometheus metrics via `prometheus-fastapi-instrumentator`: default RED
metrics (request rate, error rate, duration) exposed at `/metrics`. See
docs/adr/0008-observability-tracing-metrics-dashboards.md.

Disabled by default (`Settings.METRICS_ENABLED`) -- see that flag's
docstring in backend/config/settings.py for why: the instrumentator
registers collectors into the process-global Prometheus registry, and the
test suite calls `create_app()` many times in one process.
"""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from backend.config.settings import Settings


def instrument_app(app: FastAPI, settings: Settings) -> None:
    """Expose `/metrics` on `app` if `settings.METRICS_ENABLED`; a no-op otherwise."""
    if not settings.METRICS_ENABLED:
        return

    Instrumentator().instrument(app).expose(app, include_in_schema=False)
