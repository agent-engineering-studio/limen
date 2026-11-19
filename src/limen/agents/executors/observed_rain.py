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
l'osservata e il motore resta sulla previsione. Un fotogramma che si è mosso
più di quanto possa piovere in mezz'ora rispetto a quello prima (#235) si
giudica intero (#429): se è lui ad aver aggiunto pioggia si usa il precedente.
I pixel sopra il record italiano della finestra (#643) diventano «non
misurato».
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.integrations.dpc import (
    CUM_PERIOD,
    RainGrid,
    frame_quality,
    get_cum_at,
    get_latest_cum,
)

log = get_logger(__name__)


class ObservedRainExecutor(Executor):
    """Popola ``flood_rain_observed_by_cell`` dalla cumulata radar DPC."""

    def __init__(
        self,
        *,
        hours: int,
        max_age_minutes: int,
        max_step_mm: float,
        fetch: Callable[[int], Awaitable[RainGrid | None]] = get_latest_cum,
        fetch_at: Callable[[int, datetime], Awaitable[RainGrid | None]] = get_cum_at,
    ) -> None:
        super().__init__(name="ObservedRain")
        self._hours = hours
        self._max_age_s = max_age_minutes * 60
        self._max_step_mm = max_step_mm
        self._fetch = fetch
        self._fetch_at = fetch_at

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        grid = await self._fetch(self._hours)
        if grid is None or self._too_far(grid, ctx):
            return ctx
        grid = await self._checked(grid, ctx.aoi_id)
        if self._too_far(grid, ctx):
            return ctx
        cells = [c for c in ctx.cell_ids if c in ctx.cell_centroids]
        values = grid.sample([ctx.cell_centroids[c] for c in cells])
        observed = {c: v for c, v in zip(cells, values, strict=True) if v is not None}
        log.info(
            "executor.observed_rain.done",
            aoi_id=ctx.aoi_id,
            hours=self._hours,
            observed_at=grid.time.isoformat(),
            cells=len(observed),
            max_mm=round(max(observed.values()), 1) if observed else None,
        )
        return ctx.with_update(flood_rain_observed_by_cell=observed)

    def _too_far(self, grid: RainGrid, ctx: MonitoringContext) -> bool:
        if abs((ctx.valuation_time - grid.time).total_seconds()) <= self._max_age_s:
            return False
        log.info(
            "executor.observed_rain.skip",
            aoi_id=ctx.aoi_id,
            reason="frame too far from valuation time",
            observed_at=grid.time.isoformat(),
        )
        return True

    async def _checked(self, grid: RainGrid, aoi_id: str) -> RainGrid:
        """Il fotogramma da usare, giudicato contro quello di mezz'ora prima.

        Il giudizio è sul fotogramma intero (#429): la regola per pixel di
        #235 toglieva la cima di una campana corrotta e ne lasciava passare i
        fianchi. Il segno del salto dice quale dei due è sbagliato: ogni
        corruzione vista finora *aggiunge* pioggia, e respinto questo si usa il
        precedente. Poi, sul fotogramma usato, i pixel sopra il record italiano
        della finestra diventano «non misurato» (#643): questo non ha bisogno
        del precedente, quindi senza il precedente il fotogramma non passa più
        com'è anche se il guasto supera ogni pioggia possibile.
        """
        previous = await self._fetch_at(self._hours, grid.time - CUM_PERIOD)
        if previous is None:
            log.warning(
                "executor.observed_rain.unchecked",
                aoi_id=aoi_id,
                observed_at=grid.time.isoformat(),
            )
        q = frame_quality(grid, previous, max_step=self._max_step_mm)
        if q.verdict not in (None, "consistent") or q.beyond_record:
            log.warning(
                "executor.observed_rain.inconsistent",
                aoi_id=aoi_id,
                observed_at=grid.time.isoformat(),
                used_at=q.grid.time.isoformat(),
                verdict=q.verdict,
                pixels=q.jumps,
                beyond_record=q.beyond_record,
                max_step_mm=self._max_step_mm,
            )
        return q.grid
