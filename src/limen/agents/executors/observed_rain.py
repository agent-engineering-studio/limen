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
from datetime import datetime, timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.regional_thresholds import NowcastBlock, RadarCiecoBlock
from limen.integrations.dpc import (
    CUM_PERIOD,
    RainGrid,
    frame_quality,
    get_cum_at,
    get_latest_cum,
    osservata,
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
        blind: RadarCiecoBlock | None = None,
        rarity: bool = False,
        nowcast: NowcastBlock | None = None,
    ) -> None:
        super().__init__(name="ObservedRain")
        self._hours = hours
        self._max_age_s = max_age_minutes * 60
        self._max_step_mm = max_step_mm
        self._fetch = fetch
        self._fetch_at = fetch_at
        self._blind = blind
        self._rarity = rarity
        self._nowcast = nowcast

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        grid = await self._fetch(self._hours)
        if grid is None or self._too_far(grid, ctx):
            return ctx
        grid = await self._checked(grid, ctx.aoi_id)
        if self._too_far(grid, ctx):
            return ctx
        cells = [c for c in ctx.cell_ids if c in ctx.cell_centroids]
        punti = [ctx.cell_centroids[c] for c in cells]
        values = grid.sample(punti)
        if self._blind is not None:
            values = self._senza_zeri_ciechi(grid, punti, values, self._blind)
        observed = {c: v for c, v in zip(cells, values, strict=True) if v is not None}
        extra: dict[str, dict[str, float]] = {}
        anni = osservata.ritorno(grid, punti) if self._rarity else None
        if anni is not None:
            extra["flood_rain_observed_years_by_cell"] = {
                c: a for c, a in zip(cells, anni, strict=True) if a is not None and c in observed
            }
        if self._nowcast is not None:
            avanti = await osservata.nowcast(
                self._nowcast.minutes,
                punti,
                adesso=ctx.valuation_time,
                eta_massima=timedelta(minutes=self._nowcast.max_age_minutes),
            )
            if avanti is not None:
                extra["flood_rain_ahead_by_cell"] = {
                    c: a for c, a in zip(cells, avanti, strict=True) if a is not None
                }
        log.info(
            "executor.observed_rain.done",
            aoi_id=ctx.aoi_id,
            hours=self._hours,
            observed_at=grid.time.isoformat(),
            cells=len(observed),
            max_mm=round(max(observed.values()), 1) if observed else None,
        )
        return ctx.with_update(flood_rain_observed_by_cell=observed, **extra)

    @staticmethod
    def _senza_zeri_ciechi(
        grid: RainGrid,
        punti: list[tuple[float, float]],
        values: list[float | None],
        cieco: RadarCiecoBlock,
    ) -> list[float | None]:
        """Dove il radar vede male, una pioggia sotto ``dry_mm`` diventa «non misurata»."""
        punteggi = osservata.affidabilita(grid, punti)
        if punteggi is None:  # mappa illeggibile: si resta come senza il blocco
            return values
        return [
            None
            if v is not None and v < cieco.dry_mm and (a is None or a < cieco.min_reliability)
            else v
            for v, a in zip(values, punteggi, strict=True)
        ]

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
