"""``limen monitor-once`` — one-shot workflow runner outside FastAPI.

Wires up DB, ObjectStore (for raster refs the workflow may need), and
the resolved LLM factory, then runs :func:`build_landslide_workflow`
over a single AOI provided via ``LIMEN_MONITOR_AOI`` (or, in the
absence of that, every seeded AOI in the database).

Phase 5 will swap this scaffolding for the FastAPI HTTP trigger +
APScheduler hourly job.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from limen.agents.llm_factory.resolver import resolve_llm_factory
from limen.agents.workflows.main_workflow import (
    WorkflowDeps,
    build_landslide_workflow,
)
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)

_DEFAULT_CELL_LIMIT_ENV = "LIMEN_MONITOR_CELL_LIMIT"
_AOI_ENV = "LIMEN_MONITOR_AOI"


async def _run_for_aoi(*, aoi_id: str, deps: WorkflowDeps, cell_limit: int | None) -> None:
    wf = build_landslide_workflow(deps, cell_limit=cell_limit)
    ctx = MonitoringContext(
        aoi_id=aoi_id,
        valuation_time=datetime.now(UTC),
        enable_insitu=deps.settings.enable_insitu,
    )
    result = await wf.run(ctx)
    out = result.context
    log.info(
        "monitor_once.aoi.done",
        aoi_id=aoi_id,
        cells=len(out.cell_results),
        assessment_id=out.assessment_id,
        high_or_above=(out.assessment.cells_high_or_above if out.assessment else 0),
    )


async def run() -> int:
    cell_limit_env = os.getenv(_DEFAULT_CELL_LIMIT_ENV)
    cell_limit = int(cell_limit_env) if cell_limit_env else None
    requested_aoi = os.getenv(_AOI_ENV)

    settings = get_settings()
    deps = WorkflowDeps(llm_factory=resolve_llm_factory(settings), settings=settings)

    try:
        async with lifespan_pool():
            await run_migrations()
            if requested_aoi:
                aois = [requested_aoi]
            else:
                aois = await list_aoi_ids()
            if not aois:
                log.warning("monitor_once.no_aois", note="run `limen seed` first")
                return 0
            for aoi_id in aois:
                await _run_for_aoi(aoi_id=aoi_id, deps=deps, cell_limit=cell_limit)
    finally:
        await SharedHttpClient.aclose()
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
