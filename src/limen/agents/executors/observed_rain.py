"""La pioggia già caduta su ogni cella, dal radar DPC (#199).

Lo step dei segnali porta la pioggia **prevista**, con la finestra che parte
adesso: un nubifragio in corso ne esce mentre cade. A Melito di Porto Salvo,
la mattina del 10 ottobre 2026, la previsione dava 20 mm e la cumulata radar
delle 24 ore ne misurava 152; il trigger del radar faceva ripartire lo
scoring, e lo scoring ricalcolava sulla previsione. Qui si legge la cumulata
«Merging» (radar più pluviometri, 1 km) sul centroide di ogni cella; il
motore la somma alla previsione sulle ore che restano.

Degrada senza alzare: senza fotogramma, o con un fotogramma troppo lontano
dall'istante valutato (un replay, un backtest), nessuna cella riceve
l'osservata e il motore resta sulla previsione.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.integrations.dpc import SriGrid, get_latest_cum

log = get_logger(__name__)


class ObservedRainExecutor(Executor):
    """Popola ``flood_rain_observed_by_cell`` dalla cumulata radar DPC."""

    def __init__(
        self,
        *,
        hours: int,
        max_age_minutes: int,
        fetch: Callable[[int], Awaitable[SriGrid | None]] = get_latest_cum,
    ) -> None:
        super().__init__(name="ObservedRain")
        self._hours = hours
        self._max_age_s = max_age_minutes * 60
        self._fetch = fetch

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        grid = await self._fetch(self._hours)
        if grid is None:
            return ctx
        age = abs((ctx.valuation_time - grid.observed_at).total_seconds())
        if age > self._max_age_s:
            log.info(
                "executor.observed_rain.skip",
                aoi_id=ctx.aoi_id,
                reason="frame too far from valuation time",
                observed_at=grid.observed_at.isoformat(),
            )
            return ctx
        cells = [c for c in ctx.cell_ids if c in ctx.cell_centroids]
        values = grid.sample([ctx.cell_centroids[c] for c in cells])
        observed = {c: v for c, v in zip(cells, values, strict=True) if v is not None}
        log.info(
            "executor.observed_rain.done",
            aoi_id=ctx.aoi_id,
            hours=self._hours,
            observed_at=grid.observed_at.isoformat(),
            cells=len(observed),
            max_mm=round(max(observed.values()), 1) if observed else None,
        )
        return ctx.with_update(flood_rain_observed_by_cell=observed)
