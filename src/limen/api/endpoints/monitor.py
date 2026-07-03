"""POST /api/monitor/{aoi_id} — run the MAF workflow once for an AOI."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status

from limen.api.auth import RequireUser
from limen.api.dependencies import DepsDep
from limen.api.schemas import MonitorRequest, MonitorResponse
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)

router = APIRouter(prefix="/api/monitor", tags=["monitor"])


@router.post("/{aoi_id}", response_model=MonitorResponse)
async def run_monitor(
    aoi_id: str,
    deps: DepsDep,
    _user: RequireUser,
    body: MonitorRequest | None = None,
) -> MonitorResponse:
    """Execute the Phase-4 workflow for ``aoi_id`` and persist the result.

    Protected: requires a valid Clerk JWT when ``CLERK__ENABLED`` (open
    otherwise). The public read-only map endpoints stay unauthenticated.
    """
    body = body or MonitorRequest()
    workflow = deps.build_workflow(cell_limit=body.cell_limit)
    ctx = MonitoringContext(
        aoi_id=aoi_id,
        valuation_time=body.valuation_time or datetime.now(UTC),
        enable_insitu=deps.settings.enable_insitu,
    )
    try:
        result = await workflow.run(ctx)
    except RuntimeError as exc:
        # `AreaResolverExecutor` raises this when the AOI is unknown.
        if "AOI" in str(exc) and "not found" in str(exc):
            log.warning("monitor.aoi_missing", aoi_id=aoi_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AOI {aoi_id!r} not found",
            ) from exc
        raise

    out = result.context
    high_or_above = out.assessment.cells_high_or_above if out.assessment is not None else 0
    log.info(
        "monitor.done",
        aoi_id=aoi_id,
        cells=len(out.cell_results),
        assessment_id=out.assessment_id,
        high_or_above=high_or_above,
    )
    return MonitorResponse(
        aoi_id=aoi_id,
        assessment_id=out.assessment_id,
        assessment=out.assessment,
        cells_scored=len(out.cell_results),
        high_or_above=high_or_above,
        dispatched_alerts=list(out.dispatched_alerts),
    )
