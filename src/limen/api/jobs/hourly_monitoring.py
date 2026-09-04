"""Hourly job — run the MAF workflow for every active AOI."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)

# Lo sweep nazionale può durare più del tick orario: un secondo run
# concorrente raddoppia il carico sul DB e affama le regioni in coda.
# Il tick che trova il lock occupato salta (il prossimo riparte comunque
# stale-first, quindi nessuna regione resta indietro).
_sweep_lock = asyncio.Lock()


async def _aois_stale_first(hazard: HazardType = DEFAULT_HAZARD) -> list[str]:
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
                FROM mv_latest_risk
                WHERE hazard_type = $1
                GROUP BY aoi_id
            ) m ON m.aoi_id = a.id
            ORDER BY m.ts ASC NULLS FIRST, a.id
            """,
            hazard.value,
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
    """Sweep every enabled hazard over every AOI.

    Keyed by AOI with the cell count summed across hazards, so with a single
    hazard enabled the numbers are exactly what this job has always returned.
    The per-hazard detail is in the log line, and lands in ``job_runs`` when
    #75 ships.
    """
    out: dict[str, int] = {}
    hazards = list(deps.settings.hazards.enabled)
    if not hazards:
        log.warning("job.hourly_monitoring.no_hazards")
        return out

    for hazard in hazards:
        # Stale-first *per hazard*: each one has its own last-assessed time,
        # so ordering by a mixed timestamp would starve whichever hazard
        # happens to lag.
        aois = await _aois_stale_first(hazard)
        if not aois:
            log.info("job.hourly_monitoring.no_aois", hazard=hazard.value)
            continue
        try:
            workflow = deps.build_workflow(hazard=hazard)
        except Exception as exc:
            # A hazard that cannot be scored (no engine, no thresholds) must
            # not take the other hazards down with it.
            log.error(
                "job.hourly_monitoring.workflow_unavailable",
                hazard=hazard.value,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        for aoi_id in aois:
            ctx = MonitoringContext(
                aoi_id=aoi_id,
                hazard_type=hazard,
                valuation_time=datetime.now(UTC),
                enable_insitu=deps.settings.enable_insitu,
            )
            try:
                result = await workflow.run(ctx)
            except Exception as exc:  # never bring the scheduler down
                log.error(
                    "job.hourly_monitoring.error",
                    aoi_id=aoi_id,
                    hazard=hazard.value,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            cells = len(result.context.cell_results)
            out[aoi_id] = out.get(aoi_id, 0) + cells
            log.info(
                "job.hourly_monitoring.aoi.done",
                aoi_id=aoi_id,
                hazard=hazard.value,
                cells=cells,
                assessment_id=result.context.assessment_id,
            )
    log.info(
        "job.hourly_monitoring.done",
        hazards=[h.value for h in hazards],
        aois=len(out),
        per_aoi=out,
    )
    return out
