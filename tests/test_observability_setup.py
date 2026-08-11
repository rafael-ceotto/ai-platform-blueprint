"""Tests for observability/tracing and observability/metrics setup.

Both are disabled by default (see Settings.TRACING_ENABLED /
Settings.METRICS_ENABLED docstrings) because the process-global tracer
provider and Prometheus registry can't safely be instrumented twice, and
the rest of the suite calls create_app() many times in one process. Only
one test here enables them, against an isolated FastAPI app, to keep
registration single.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config.settings import Settings
from observability.metrics import setup as metrics
from observability.tracing import setup as tracing


def _settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]


def test_tracing_instrument_app_is_a_noop_when_disabled() -> None:
    app = FastAPI()
    tracing.instrument_app(app, _settings(TRACING_ENABLED=False))

    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is False


def test_metrics_instrument_app_is_a_noop_when_disabled() -> None:
    app = FastAPI()
    metrics.instrument_app(app, _settings(METRICS_ENABLED=False))

    with TestClient(app) as client:
        response = client.get("/metrics")

    assert response.status_code == 404


def test_tracing_and_metrics_instrument_app_when_enabled() -> None:
    # Exercises the real OTLP exporter against an endpoint nothing is
    # listening on -- expect noisy "connection refused" warnings on
    # stderr from the BatchSpanProcessor's background export thread.
    # That's the real exporter behaving correctly, not a test failure.
    app = FastAPI()
    settings = _settings(
        TRACING_ENABLED=True,
        METRICS_ENABLED=True,
        OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317",
    )

    provider = tracing.instrument_app(app, settings)
    metrics.instrument_app(app, settings)

    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is True

    try:
        with TestClient(app) as client:
            response = client.get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
    finally:
        # Stop the background export thread now instead of leaving it
        # retrying against an unreachable endpoint until process exit.
        assert provider is not None
        provider.shutdown()
