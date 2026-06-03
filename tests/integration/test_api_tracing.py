"""Tracing setup smoke test using an in-memory exporter."""

from __future__ import annotations

import httpx
import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.data.db import get_pool
from limen.observability.tracing import setup_tracing

pytestmark = pytest.mark.integration


async def test_request_emits_a_span(reset_db: None, pg_pool: object) -> None:
    settings = Settings.model_validate({})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    # ASGITransport doesn't auto-fire lifespan — set state directly.
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test wiring"

    exporter = InMemorySpanExporter()
    setup_tracing(app, in_memory_exporter=exporter, service_name="limen-api-test")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200

    # The FastAPI instrumentor flushes the span when the response is sent.
    spans = exporter.get_finished_spans()
    assert spans, "expected at least one finished span"
    names = {s.name for s in spans}
    assert any("/health" in name or "GET" in name for name in names)
