"""Radar-nowcast trigger — short-horizon event-driven monitoring.

Every ``NOWCAST__INTERVAL_MINUTES`` the job reads the latest DPC SRI
frame (national 1 km rain intensity, 5-minute refresh). AOIs where the
radar sees rain at/above ``NOWCAST__MIN_INTENSITY_MMH`` on at least
``NOWCAST__MIN_PIXELS`` km² get their monitoring workflow run
immediately instead of waiting for the hourly tick. Alerts flow through
the normal operational path (escalation, per-cell dedup, channels) —
the radar only decides *when* to run, never *what* to score.

A cooldown skips AOIs whose latest assessment is fresher than
``NOWCAST__COOLDOWN_MINUTES``, so radar triggers and the hourly job
never pile up on the same region.
"""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire
from limen.integrations.dpc import get_latest_sri

log = get_logger(__name__)


async def _aoi_bboxes() -> list[tuple[str, tuple[float, float, float, float]]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_XMin(bbox) AS x0, ST_YMin(bbox) AS y0,
                   ST_XMax(bbox) AS x1, ST_YMax(bbox) AS y1
            FROM aoi ORDER BY id
            """
        )
    return [
        (str(r["id"]), (float(r["x0"]), float(r["y0"]), float(r["x1"]), float(r["y1"])))
        for r in rows
    ]


async def _recently_assessed(aoi_id: str, *, cooldown_minutes: int) -> bool:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = $1
              AND ra.computed_at >= now() - make_interval(mins => $2)
            LIMIT 1
            """,
            aoi_id,
            cooldown_minutes,
        )
    return row is not None


async def run_nowcast_monitoring(deps: AppDependencies) -> dict[str, float]:
    """Radar sweep; returns max mm/h per triggered AOI."""
    cfg = deps.settings.nowcast
    sri = await get_latest_sri()
    if sri is None:
        log.info("job.nowcast.skip", reason="sri unavailable (degraded)")
        return {}

    triggered: dict[str, float] = {}
    for aoi_id, bbox in await _aoi_bboxes():
        peak, hot_pixels = sri.max_intensity(bbox, threshold_mmh=cfg.min_intensity_mmh)
        if peak < cfg.min_intensity_mmh or hot_pixels < cfg.min_pixels:
            continue
        if await _recently_assessed(aoi_id, cooldown_minutes=cfg.cooldown_minutes):
            log.info("job.nowcast.cooldown", aoi_id=aoi_id, peak_mmh=round(peak, 1))
            continue
        log.info(
            "job.nowcast.triggered",
            aoi_id=aoi_id,
            peak_mmh=round(peak, 1),
            hot_pixels=hot_pixels,
            observed_at=sri.observed_at.isoformat(),
        )
        try:
            workflow = deps.build_workflow()
            ctx = MonitoringContext(
                aoi_id=aoi_id,
                valuation_time=datetime.now(UTC),
                enable_insitu=deps.settings.enable_insitu,
            )
            result = await workflow.run(ctx)
            triggered[aoi_id] = round(peak, 1)
            log.info(
                "job.nowcast.aoi.done",
                aoi_id=aoi_id,
                cells=len(result.context.cell_results),
                assessment_id=result.context.assessment_id,
            )
        except Exception as exc:  # never bring the scheduler down
            log.error(
                "job.nowcast.error",
                aoi_id=aoi_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    log.info("job.nowcast.done", triggered=triggered)
    return triggered
