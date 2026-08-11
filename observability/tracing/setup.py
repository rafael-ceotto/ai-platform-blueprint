"""OpenTelemetry distributed tracing: FastAPI + httpx instrumentation,
exported via OTLP/gRPC to Jaeger. See
docs/adr/0008-observability-tracing-metrics-dashboards.md.

Disabled by default (`Settings.TRACING_ENABLED`) -- see that flag's
docstring in backend/config/settings.py for why: instrumenting more than
one FastAPI app in the same process isn't safe against the global tracer
provider, and the test suite calls `create_app()` many times.
"""

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from backend.config.settings import Settings


def configure_tracing(settings: Settings) -> TracerProvider:
    """Build and register the process-wide TracerProvider, and instrument
    httpx (a global patch, so it covers OllamaClient's per-call
    `httpx.AsyncClient` instances automatically)."""
    resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()

    return provider


def instrument_app(app: FastAPI, settings: Settings) -> TracerProvider | None:
    """Wire tracing into `app` if `settings.TRACING_ENABLED`; a no-op otherwise.

    Returns the `TracerProvider` (or `None` when disabled) so callers --
    tests, mainly -- can `.shutdown()` it deterministically instead of
    leaving its background export thread running until process exit.
    """
    if not settings.TRACING_ENABLED:
        return None

    provider = configure_tracing(settings)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    return provider
