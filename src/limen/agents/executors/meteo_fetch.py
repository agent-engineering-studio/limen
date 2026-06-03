"""Open-Meteo (cache-first) fetch + API_30 archive lookup."""

from __future__ import annotations

from datetime import timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient

log = get_logger(__name__)


class MeteoFetchExecutor(Executor):
    """Fills the context with hourly meteo samples + API_30 estimate."""

    def __init__(
        self,
        *,
        client: CachedOpenMeteoClient | None = None,
        window_hours: int = 48,
        api_days: int = 30,
    ) -> None:
        super().__init__(name="MeteoFetch")
        self._client = client or CachedOpenMeteoClient()
        self._window_hours = window_hours
        self._api_days = api_days

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.bbox is None:
            log.warning("executor.meteo_fetch.skip", reason="no bbox in ctx")
            return ctx

        window_start = ctx.valuation_time - timedelta(hours=self._window_hours)
        snapshot = await self._client.get_meteo_snapshot(
            aoi_id=ctx.aoi_id,
            bbox=ctx.bbox,
            window_start=window_start,
            window_end=ctx.valuation_time,
        )
        api = await self._client.get_api(
            aoi_id=ctx.aoi_id,
            bbox=ctx.bbox,
            as_of=ctx.valuation_time.date(),
            days=self._api_days,
        )

        samples = tuple(snapshot.samples) if snapshot is not None else ()
        centroid = (snapshot.centroid_lon, snapshot.centroid_lat) if snapshot is not None else None
        api_mm = api.get(f"api_{self._api_days}d") if api else None
        soil = None
        if snapshot is not None and snapshot.samples:
            sm_vals = [
                s.soil_moisture_0_7_cm
                for s in snapshot.samples
                if s.soil_moisture_0_7_cm is not None
            ]
            if sm_vals:
                soil = float(sum(sm_vals) / len(sm_vals))

        log.info(
            "executor.meteo_fetch",
            aoi_id=ctx.aoi_id,
            samples=len(samples),
            api_30_mm=api_mm,
            soil=soil,
            degraded=snapshot is None,
        )
        return ctx.with_update(
            meteo_centroid_lonlat=centroid,
            meteo_samples=samples,
            api_30_mm=api_mm,
            soil_moisture_0_7=soil,
        )
