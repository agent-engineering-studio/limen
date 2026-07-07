"""Hourly job — run the MAF workflow for every active AOI."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire

log = get_logger(__name__)

# Lo sweep nazionale può durare più del tick orario: un secondo run
# concorrente raddoppia il carico sul DB e affama le regioni in coda.
# Il tick che trova il lock occupato salta (il prossimo riparte comunque
# stale-first, quindi nessuna regione resta indietro).
_sweep_lock = asyncio.Lock()


async def _aois_stale_first() -> list[str]:
    """AOIs ordered by oldest assessment first (never-assessed in testa).

    Lo sweep nazionale dura più del tick orario: con l'ordine alfabetico
    fisso le regioni in coda (Toscana, Veneto, …) non venivano MAI
    valutate — ogni tick ripartiva dalla testa.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id
            FROM aoi a
            LEFT JOIN (
                SELECT aoi_id, MAX(computed_at) AS ts
                FROM mv_latest_risk GROUP BY aoi_id
            ) m ON m.aoi_id = a.id
            ORDER BY m.ts ASC NULLS FIRST, a.id
            """
        )
    return [str(r["id"]) for r in rows]


async def run_hourly_monitoring(deps: AppDependencies) -> dict[str, int]:
    """Run the workflow over every AOI; return per-AOI cell counts."""
    if _sweep_lock.locked():
        log.info("job.hourly_monitoring.skip", reason="previous sweep still running")
        return {}
    async with _sweep_lock:
        return await _run_sweep(deps)


async def _run_sweep(deps: AppDependencies) -> dict[str, int]:
    aois = await _aois_stale_first()
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
