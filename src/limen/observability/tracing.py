"""OpenTelemetry tracing setup.

Wires the FastAPI / asyncpg / httpx instrumentors and an OTLP HTTP
exporter (configurable via :class:`Settings` or ``OTEL_EXPORTER_OTLP_ENDPOINT``).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

from limen.core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

log = get_logger(__name__)

_TRACER_PROVIDER_CONFIGURED = False


def setup_tracing(
    app: FastAPI | None = None,
    *,
    otlp_endpoint: str | None = None,
    service_name: str = "limen-api",
    in_memory_exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Configure tracing for the process.

    Args:
        app: FastAPI app to instrument. ``None`` skips the FastAPI
            instrumentor (useful for tests or workers).
        otlp_endpoint: OTLP/HTTP endpoint. If both ``otlp_endpoint`` and
            ``in_memory_exporter`` are ``None``, no exporter is attached
            — spans are produced and dropped, which is the right default
            for unit tests.
        service_name: ``service.name`` resource attribute.
        in_memory_exporter: Optional exporter (used by tests to assert
            spans without standing up an OTLP collector).
    """
    global _TRACER_PROVIDER_CONFIGURED

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if in_memory_exporter is not None:
        # Tests want spans visible immediately — Simple processor flushes
        # on every ``on_end``, BatchSpanProcessor would buffer.
        provider.add_span_processor(SimpleSpanProcessor(in_memory_exporter))
    elif otlp_endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))

    # Always (re-)set the global tracer provider so tests can swap exporters
    # cleanly between runs without leaking the prior provider's spans.
    trace.set_tracer_provider(provider)
    _TRACER_PROVIDER_CONFIGURED = True

    # Instrumentors are idempotent (uninstrument before re-instrument keeps
    # tests deterministic). Suppress on first call where uninstrument is a
    # no-op anyway.
    with contextlib.suppress(Exception):
        AsyncPGInstrumentor().uninstrument()  # type: ignore[no-untyped-call]
    AsyncPGInstrumentor().instrument()  # type: ignore[no-untyped-call]

    with contextlib.suppress(Exception):
        HTTPXClientInstrumentor().uninstrument()
    HTTPXClientInstrumentor().instrument()

    if app is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    log.info(
        "tracing.setup",
        service_name=service_name,
        otlp_endpoint=otlp_endpoint,
        in_memory_exporter=type(in_memory_exporter).__name__ if in_memory_exporter else None,
    )
    return provider
