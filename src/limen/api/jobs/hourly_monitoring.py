"""Hourly job — run the MAF workflow for every active AOI."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.repos.aoi_repo import list_aoi_ids

log = get_logger(__name__)


async def run_hourly_monitoring(deps: AppDependencies) -> dict[str, int]:
    """Run the workflow over every AOI; return per-AOI cell counts."""
    aois = await list_aoi_ids()
    out: dict[str, int] = {}
    if not aois:
        log.info("job.hourly_monitoring.no_aois")
        return out

    workflow = deps.build_workflow()
    for aoi_id in aois:
        ctx = MonitoringContext(
            aoi_id=aoi_id,
            valuation_time=datetime.now(UTC),
            enable_insitu=deps.settings.enable_insitu,
        )
        try:
            result = await workflow.run(ctx)
        except Exception as exc:  # never bring the scheduler down
            log.error(
                "job.hourly_monitoring.error",
                aoi_id=aoi_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        cells = len(result.context.cell_results)
        out[aoi_id] = cells
        log.info(
            "job.hourly_monitoring.aoi.done",
            aoi_id=aoi_id,
            cells=cells,
            assessment_id=result.context.assessment_id,
        )
    log.info("job.hourly_monitoring.done", aois=len(aois), per_aoi=out)
    return out
