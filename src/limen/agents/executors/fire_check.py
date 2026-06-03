"""EFFIS fire perimeters → months_since_fire (AOI-level approximation).

The engine's post-fire window is a Gaussian centred at 6 months. We
report the **most recent fire** intersecting the AOI; if no recent
fire is in the database, the field stays ``None`` (the engine then
returns 0 for the F component, which is the correct neutral).
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire

log = get_logger(__name__)


_QUERY_SQL = """
SELECT MAX(fp.fire_date) AS last_fire
FROM fire_perimeters fp
JOIN aoi a ON ST_Intersects(a.geom, fp.geom)
WHERE a.id = $1
"""


class FireCheckExecutor(Executor):
    """Sets :attr:`MonitoringContext.months_since_fire` from EFFIS data."""

    def __init__(self) -> None:
        super().__init__(name="FireCheck")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        async with acquire() as conn:
            row = await conn.fetchrow(_QUERY_SQL, ctx.aoi_id)

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
