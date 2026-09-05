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
        per_node: bool = False,
    ) -> FloodSignals: ...


class FloodForecastFetchExecutor(Executor):
    """Populate the context's dynamic flood signals (opt-in, degrades to None)."""

    def __init__(
        self,
        *,
        client: _FloodClient | None = None,
        horizon_hours: int = 72,
        per_node: bool = False,
    ) -> None:
        super().__init__(name="FloodForecastFetch")
        self._client: _FloodClient = client if client is not None else OpenMeteoFloodClient()
        self._horizon_hours = horizon_hours
        # I due segnali campionati per nodo invece che al centroide dell'AOI.
        # Acceso per il pericolo alluvione, dove sono il motore; spento per le
        # frane, dove il centroide alimenta un bonus opzionale al componente H
        # e cambiarlo sposterebbe i numeri del campione V1 senza un backtest.
        self._per_node = per_node

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.bbox is None:
            log.warning("executor.flood_forecast.skip", reason="no bbox in ctx")
            return ctx
        sig = await self._client.fetch_signals(
            bbox=ctx.bbox,
            valuation_time=ctx.valuation_time,
            horizon_hours=self._horizon_hours,
            per_node=self._per_node,
        )
        log.info(
            "executor.flood_forecast.done",
            aoi_id=ctx.aoi_id,
            rain_72h_mm=sig.rain_72h_mm,
            river_discharge_ratio=sig.river_discharge_ratio,
            coastal_surge_norm=sig.coastal_surge_norm,
            per_node=self._per_node,
            nodes=len(sig.nodes),
            nodes_with_river=sum(1 for r in sig.river_ratio_by_node if r is not None),
        )
        return ctx.with_update(
            flood_forecast_rain_72h_mm=sig.rain_72h_mm,
            river_discharge_ratio=sig.river_discharge_ratio,
            coastal_surge_norm=sig.coastal_surge_norm,
            flood_nodes=sig.nodes,
            flood_rain_by_node=sig.rain_by_node,
            flood_river_ratio_by_node=sig.river_ratio_by_node,
        )
