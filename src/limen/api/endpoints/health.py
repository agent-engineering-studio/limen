"""Liveness + readiness endpoints.

``/health`` reports component reachability (pool, cache, LLM provider).
``/ready`` is the conservative gate — it returns 503 until the pool is
up and migrations have been applied. The lifespan flips
``app.state.ready`` once both are true.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Request, Response, status

from limen.api.dependencies import DepsDep
from limen.api.schemas import HealthResponse, ReadinessResponse
from limen.core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(deps: DepsDep) -> HealthResponse:
    """Liveness probe — always 200 once the lifespan finishes building deps."""
    pool_ok = False
    cache_ok = False
    try:
        async with deps.pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        pool_ok = True
    except Exception as exc:
        log.warning("health.pool", error=str(exc))

    try:
        await deps.cache.set_json("limen:health", {"ok": True}, ttl_seconds=10)
        await deps.cache.get_json("limen:health")
        cache_ok = True
    except Exception as exc:
        log.warning("health.cache", error=str(exc))

    return HealthResponse(
        status="ok" if pool_ok and cache_ok else "degraded",
        pool=pool_ok,
        cache=cache_ok,
        llm_provider=deps.llm_factory.provider,
    )


@router.get("/ready")
async def ready(request: Request, response: Response) -> ReadinessResponse:
    """Readiness gate — 503 until pool + migrations are confirmed."""
    is_ready = bool(getattr(request.app.state, "ready", False))
    deps = getattr(request.app.state, "deps", None)
    pool_ok = False
    if deps is not None:
        try:
            async with deps.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            pool_ok = True
        except Exception as exc:
            log.warning("ready.pool", error=str(exc))
    if not is_ready or not pool_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="not_ready",
            pool=pool_ok,
            migrations=is_ready,
            detail="lifespan still bootstrapping or pool unreachable",
        )
    return ReadinessResponse(
        status="ready",
        pool=True,
        migrations=True,
        detail=cast(str, getattr(request.app.state, "ready_detail", "ok")),
    )
