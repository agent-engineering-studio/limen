"""INGV events (last N days) → seismic history for the engine.

Reads pre-ingested events from ``seismic_events`` rather than calling
INGV live: the live ingestion job (Phase 2) runs separately on a
schedule (Phase 5 wires APScheduler). At workflow execution time we
just consume what's already in the DB so the scoring path stays fast.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import SeismicHistoryEvent
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire

log = get_logger(__name__)


# A coarse PGA estimate for events without a stored ShakeMap raster:
# GMPE attenuation is out of scope for V1 (later prompt). We assume a
# nominal PGA equal to ``0.05 g * 10^((mag - 4.5) / 1.5)`` clipped at
# 1.0 g — good enough as an order-of-magnitude pre-filter; the
# engine's seismic_factor sigmoid handles the rest.
def _nominal_pga_g(magnitude: float) -> float:
    pga = 0.05 * (10.0 ** ((magnitude - 4.5) / 1.5))
    return float(min(max(pga, 0.0), 1.0))


_QUERY_SQL = """
SELECT id, origin_time, magnitude, depth_km, geom
FROM seismic_events
WHERE origin_time >= $1 AND origin_time <= $2
  AND magnitude >= $3
"""


class SeismicCheckExecutor(Executor):
    """Loads recent seismic events into the context."""

    def __init__(self, lookback_days: int | None = None) -> None:
        super().__init__(name="SeismicCheck")
        self._lookback_days = lookback_days

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        cfg = load_regional_thresholds().seismic
        lookback = self._lookback_days or cfg.lookback_days
        end: datetime = ctx.valuation_time
        start = end - timedelta(days=lookback)

        async with acquire() as conn:
            rows = await conn.fetch(_QUERY_SQL, start, end, cfg.min_magnitude)

        history: list[SeismicHistoryEvent] = []
        for r in rows:
            mag = float(r["magnitude"])
            history.append(
                SeismicHistoryEvent(
                    event_id=str(r["id"]),
                    origin_time=r["origin_time"],
                    magnitude=mag,
                    distance_km=0.0,  # AOI-centroid distance not modelled in V1
                    pga_g=_nominal_pga_g(mag),
                )
            )

        log.info(
            "executor.seismic_check",
            aoi_id=ctx.aoi_id,
            events=len(history),
            window_start=start.isoformat(),
            window_end=end.isoformat(),
        )
        return ctx.with_update(seismic_events=tuple(history))
