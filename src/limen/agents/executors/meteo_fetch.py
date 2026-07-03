"""Open-Meteo (cache-first) fetch + API_30 archive lookup."""

from __future__ import annotations

from datetime import timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient
from limen.integrations.openmeteo.grid import build_rain_nodes

log = get_logger(__name__)


class MeteoFetchExecutor(Executor):
    """Fills the context with hourly meteo samples + API_30 estimate.

    Besides the AOI-centroid snapshot (soil moisture + fallback rainfall),
    it samples precipitation on a node grid over the bbox
    (``rain_node_deg`` spacing) so the assembler can give each cell the
    rainfall of its nearest node — a single regional centroid misses the
    localized convective rain that actually triggers landslides (measured:
    13 mm at the Puglia centroid vs 77 mm at the truth cells, Mar 2009).
    ``rain_node_deg=0`` disables the grid (centroid-only, previous
    behaviour); a failed grid fetch degrades the same way.
    """

    def __init__(
        self,
        *,
        client: CachedOpenMeteoClient | None = None,
        window_hours: int = 48,
        api_days: int = 30,
        rain_node_deg: float = 0.25,
    ) -> None:
        super().__init__(name="MeteoFetch")
        self._client = client or CachedOpenMeteoClient()
        self._window_hours = window_hours
        self._api_days = api_days
        self._rain_node_deg = rain_node_deg

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

        rain_nodes: tuple[tuple[float, float], ...] = ()
        rainfall_by_node: tuple[tuple[object, ...], ...] = ()
        if self._rain_node_deg > 0:
            nodes = build_rain_nodes(ctx.bbox, spacing=self._rain_node_deg)
            grid = await self._client.get_rainfall_grid(
                nodes=nodes,
                window_start=window_start,
                window_end=ctx.valuation_time,
                use_archive=False,
            )
            if len(grid) == len(nodes) and any(grid):
                rain_nodes = tuple(nodes)
                rainfall_by_node = tuple(tuple(series) for series in grid)
            else:
                log.warning(
                    "executor.meteo_fetch.grid_degraded",
                    aoi_id=ctx.aoi_id,
                    nodes=len(nodes),
                    series=len(grid),
                )

        samples = tuple(snapshot.samples) if snapshot is not None else ()
        centroid = (snapshot.centroid_lon, snapshot.centroid_lat) if snapshot is not None else None
        api_mm = api.get(f"api_{self._api_days}d") if api else None
        soil = None
        snow_depth = None
        if snapshot is not None and snapshot.samples:
            depths = [s.snow_depth_m for s in snapshot.samples if s.snow_depth_m is not None]
            if depths:
                snow_depth = float(max(depths))
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
            rain_nodes=len(rain_nodes),
            api_30_mm=api_mm,
            soil=soil,
            degraded=snapshot is None,
        )
        return ctx.with_update(
            meteo_centroid_lonlat=centroid,
            meteo_samples=samples,
            rain_nodes=rain_nodes,
            rainfall_by_node=rainfall_by_node,
            api_30_mm=api_mm,
            soil_moisture_0_7=soil,
            snow_depth_m=snow_depth,
        )
