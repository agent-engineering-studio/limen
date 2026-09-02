"""Burnt areas → months_since_fire (AOI-level approximation).

The engine's post-fire window is a Gaussian centred at 6 months. We
report the **most recent fire** affecting the AOI; if no recent fire is
in the database, the field stays ``None`` (the engine then returns 0 for
the F component, which is the correct neutral).

Two sources are combined, newest wins:

* ``fire_perimeters`` — EFFIS burnt-area polygons: consolidated, areal,
  but published days to weeks after the event.
* ``fire_hotspots`` — NASA FIRMS active-fire detections: point-wise, ~3 h
  latency, so F opens right when the post-fire risk peaks. A single
  detection is not trusted (industrial flares, sun glint): at least
  ``min_hotspots`` detections on the same day inside the AOI are
  required, which is what makes this safe to read as "it burnt here".

The engine is untouched — ``post_fire_factor`` stays pure; only the
bundle assembly changes.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire

log = get_logger(__name__)


# GREATEST ignores NULL operands in PostgreSQL, so an AOI with only one
# of the two sources still yields that source's date.
_QUERY_SQL = """
SELECT GREATEST(
    (
        SELECT MAX(fp.fire_date)
        FROM fire_perimeters fp
        JOIN aoi a ON ST_Intersects(a.geom, fp.geom)
        WHERE a.id = $1
    ),
    (
        SELECT MAX(clustered.acq_date)
        FROM (
            SELECT fh.acq_date
            FROM fire_hotspots fh
            JOIN aoi a ON ST_Intersects(a.geom, fh.geom)
            WHERE a.id = $1
            GROUP BY fh.acq_date
            HAVING COUNT(*) >= $2
        ) AS clustered
    )
) AS last_fire
"""


class FireCheckExecutor(Executor):
    """Sets :attr:`MonitoringContext.months_since_fire` from EFFIS + FIRMS."""

    def __init__(self, *, min_hotspots: int | None = None) -> None:
        super().__init__(name="FireCheck")
        self._min_hotspots = (
            min_hotspots if min_hotspots is not None else get_settings().firms.min_hotspots
        )

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        async with acquire() as conn:
            row = await conn.fetchrow(_QUERY_SQL, ctx.aoi_id, self._min_hotspots)

        last_fire = row["last_fire"] if row else None
        if last_fire is None:
            log.info("executor.fire_check", aoi_id=ctx.aoi_id, months_since_fire=None)
            return ctx.with_update(months_since_fire=None)

        delta_days = (ctx.valuation_time.date() - last_fire).days
        months = max(0.0, delta_days / 30.0)
        window_max = load_regional_thresholds().post_fire.window_months_max
        if months > window_max:
            # Out of the amplification window — record but neutralise.
            log.info(
                "executor.fire_check.window_expired",
                aoi_id=ctx.aoi_id,
                months_since_fire=months,
                window_max=window_max,
            )
            return ctx.with_update(months_since_fire=None)

        log.info(
            "executor.fire_check",
            aoi_id=ctx.aoi_id,
            months_since_fire=months,
            last_fire=str(last_fire),
        )
        return ctx.with_update(months_since_fire=months)
