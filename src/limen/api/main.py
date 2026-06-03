"""FastAPI app factory + lifespan.

Lifespan responsibilities (in order):

1. Configure structlog (already done in :mod:`limen.cli.main` when the
   CLI launches us, but we re-configure idempotently when the app is
   imported standalone).
2. Initialise the asyncpg pool.
3. Run pending migrations (idempotent runner from Prompt 1).
4. Build :class:`AppDependencies` (LLM factory resolved here).
5. Start APScheduler + register periodic jobs.
6. Mark ``app.state.ready = True``.

Shutdown is the inverse: stop scheduler → close pool → close shared
httpx client.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from apscheduler import AsyncScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from limen.api.dependencies import AppDependencies
from limen.api.endpoints import all_routers
from limen.api.jobs.registration import register_jobs
from limen.config.settings import Settings, get_settings
from limen.core.logging import configure_logging, get_logger
from limen.data.db import close_pool, init_pool
from limen.data.migrate import run_migrations
from limen.integrations._http import SharedHttpClient
from limen.observability.tracing import setup_tracing

if TYPE_CHECKING:
    from limen.agents.llm_factory.base import LlmClientFactory

log = get_logger(__name__)


@asynccontextmanager
async def _lifespan_default(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    pool = await init_pool(settings.db)
    await run_migrations()
    deps = await AppDependencies.build(pool=pool, settings=settings)
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "pool + migrations OK"

    scheduler = AsyncScheduler()
    app.state.scheduler = scheduler
    await scheduler.__aenter__()
    await register_jobs(scheduler, deps)
    await scheduler.start_in_background()
    log.info("api.lifespan.started")

    try:
        yield
    finally:
        with contextlib.suppress(Exception):
            await scheduler.stop()
        with contextlib.suppress(Exception):
            await scheduler.__aexit__(None, None, None)
        await SharedHttpClient.aclose()
        await close_pool()
        app.state.ready = False
        log.info("api.lifespan.stopped")


def _build_lifespan_for(deps: AppDependencies, scheduler: AsyncScheduler | None):  # type: ignore[no-untyped-def]
    """Wrap a pre-built deps + optional scheduler into a lifespan.

    Tests use this to inject :class:`StubLlmClientFactory` and to skip
    scheduler startup (the scheduler is exercised in dedicated tests).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.deps = deps
        app.state.ready = True
        app.state.ready_detail = "test wiring"
        app.state.scheduler = scheduler
        log.info("api.lifespan.started", mode="injected")
        try:
            yield
        finally:
            app.state.ready = False
            log.info("api.lifespan.stopped", mode="injected")

    return lifespan


def _apply_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )


def _register_routes(app: FastAPI) -> None:
    for router in all_routers():
        app.include_router(router)


def build_app(
    *,
    settings: Settings | None = None,
    llm_factory: LlmClientFactory | None = None,  # noqa: ARG001 — reserved for future use
) -> FastAPI:
    """Construct the production-shaped FastAPI app.

    Uses the default lifespan (boots the pool, applies migrations,
    builds deps, starts APScheduler). Pass ``llm_factory`` only when
    you want to force a specific provider while still using the
    default lifespan — most tests prefer :func:`build_app_with_deps`.
    """
    s = settings or get_settings()
    app = FastAPI(
        title="Limen — landslide-risk monitoring API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan_default,
    )
    _apply_middleware(app, s)
    _register_routes(app)
    if s.api.otel_otlp_endpoint:
        setup_tracing(
            app,
            otlp_endpoint=s.api.otel_otlp_endpoint,
            service_name=s.api.otel_service_name,
        )
    return app


def build_app_with_deps(
    deps: AppDependencies,
    *,
    scheduler: AsyncScheduler | None = None,
) -> FastAPI:
    """Construct a FastAPI app wired with a pre-built :class:`AppDependencies`.

    The test path: build the deps (with a stub LLM factory + the
    testcontainer pool), then build the app around them. No APScheduler
    is started by default — tests exercise the scheduler separately.
    """
    s = deps.settings
    app = FastAPI(
        title="Limen — landslide-risk monitoring API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_build_lifespan_for(deps, scheduler),
    )
    _apply_middleware(app, s)
    _register_routes(app)
    if s.api.otel_otlp_endpoint:
        setup_tracing(
            app,
            otlp_endpoint=s.api.otel_otlp_endpoint,
            service_name=s.api.otel_service_name,
        )
    return app


# Convenience for `limen serve` / uvicorn factory-style discovery.
def factory() -> FastAPI:  # pragma: no cover
    return build_app()
