"""Opt-in fetch of the dynamic flood signals into the context (issue #8).

Runs after MeteoFetch when ``enable_flood_forecast`` is set. Reads the AOI-level
forecast flood signals (pluvial rain, GloFAS river discharge, marine surge) and
stores them on the context; the assembler copies them onto each cell bundle.
Neutral degradation: a missing signal stays ``None`` — never raises.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.integrations.openmeteo.flood import FloodSignals, OpenMeteoFloodClient

log = get_logger(__name__)


class _FloodClient(Protocol):
    async def fetch_signals(
        self,
        *,
        bbox: tuple[float, float, float, float],
        valuation_time: datetime,
        horizon_hours: int = 72,
        basin_max: bool = False,
    ) -> FloodSignals: ...


class FloodForecastFetchExecutor(Executor):
    """Populate the context's dynamic flood signals (opt-in, degrades to None)."""

    def __init__(
        self,
        *,
        client: _FloodClient | None = None,
        horizon_hours: int = 72,
        basin_max: bool = False,
    ) -> None:
        super().__init__(name="FloodForecastFetch")
        self._client: _FloodClient = client or OpenMeteoFloodClient()
        self._horizon_hours = horizon_hours
        # Il ramo fluviale campionato sul bacino invece che sul centroide.
        # Acceso per il pericolo alluvione, dove è metà del motore; spento per
        # le frane, dove è un bonus opzionale al componente H e cambiarlo
        # sposterebbe i numeri del campione V1 senza un backtest.
        self._basin_max = basin_max

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.bbox is None:
            log.warning("executor.flood_forecast.skip", reason="no bbox in ctx")
            return ctx
        sig = await self._client.fetch_signals(
            bbox=ctx.bbox,
            valuation_time=ctx.valuation_time,
            horizon_hours=self._horizon_hours,
            basin_max=self._basin_max,
        )
        log.info(
            "executor.flood_forecast.done",
            aoi_id=ctx.aoi_id,
            rain_72h_mm=sig.rain_72h_mm,
            river_discharge_ratio=sig.river_discharge_ratio,
            coastal_surge_norm=sig.coastal_surge_norm,
            basin_max=self._basin_max,
        )
        return ctx.with_update(
            flood_forecast_rain_72h_mm=sig.rain_72h_mm,
            river_discharge_ratio=sig.river_discharge_ratio,
            coastal_surge_norm=sig.coastal_surge_norm,
        )
