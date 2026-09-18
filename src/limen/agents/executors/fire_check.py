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

Dalla #67 l'executor porta anche la **severità** del bruciato: la densità di
potenza radiativa del perimetro più recente, normalizzata dalla rampa in
`post_fire.frp_*`. Serve perché un incendio di chioma severo e una bruciatura
di stoppie non lasciano il versante nello stesso stato.

La severità esiste solo per i perimetri EFFIS: un cluster di hotspot senza
perimetro non ha un'area su cui dividere, e la densità è una divisione per
area. In quel caso resta `None` e il fattore F è identico a prima — non zero,
perché "non misurato" e "bruciato debolmente" sono fatti diversi.

The engine is untouched — ``post_fire_factor`` stays pure; only the
bundle assembly changes.
"""

from __future__ import annotations

from datetime import timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.post_fire import frp_severity
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire
from limen.data.repos.fire_events_repo import perimeter_severity_at

log = get_logger(__name__)


# GREATEST ignores NULL operands in PostgreSQL, so an AOI with only one
# of the two sources still yields that source's date.
#: `detection_type = 0` tiene fuori cio' che brucia ma non e' un incendio
#: (#124). FIRMS classifica la sorgente: 0 vegetazione, 1 vulcano, 2 sorgente
#: statica al suolo, 3 offshore. Senza il filtro, in Puglia il motore riteneva
#: bruciato qualcosa in **272 giorni su 366** contro i 173 veri, perche' l'ILVA
#: di Taranto e' calda tutti i giorni — e' lo stesso errore gia' corretto per
#: `fire_density`, dove la cella piu' incendiata d'Italia risultava
#: un'acciaieria. Il filtro di qualita' non la toglie e non puo': e' una misura
#: corretta di un oggetto molto caldo. Le righe con `detection_type` NULL
#: restano fuori, come per `fire_events`: sbagliare per difetto perde qualche
#: giorno, sbagliare per eccesso tiene il fattore F acceso per sempre.
#:
#: Il ramo hotspot legge `fire_hotspots` e non il rollup `fire_events`: il
#: feed NRT (`run_firms_sync`) scrive solo qui, mentre il rollup lo ricostruisce
#: la CLI storica, quindi leggerlo perderebbe proprio gli incendi delle ultime
#: ore — cioe' il motivo per cui questo ramo esiste.
#:
#: Il **limite temporale** e' invece obbligatorio. Senza, la query incrociava
#: 392.000 punti col poligono regionale a ogni tick: a cache fredda 106 s
#: contro i 30 s di `DB__COMMAND_TIMEOUT_SECONDS`, e il TimeoutError usciva
#: dall'executor facendo cadere lo sweep **intero** dell'AOI (misurato: 16
#: regioni su 20 in errore). Il limite non cambia il risultato, perche' oltre
#: `post_fire.window_months_max` il fattore F e' neutralizzato dieci righe piu'
#: sotto: si smette di leggere cio' che si sarebbe buttato via. Misurato su
#: it-abruzzo: da 3.195 blocchi letti a 115.
_QUERY_SQL = """
SELECT GREATEST(
    (
        SELECT MAX(fp.fire_date)
        FROM fire_perimeters fp
        JOIN aoi a ON ST_Intersects(a.geom, fp.geom)
        WHERE a.id = $1 AND fp.fire_date >= $3
    ),
    (
        SELECT MAX(clustered.acq_date)
        FROM (
            SELECT fh.acq_date
            FROM fire_hotspots fh
            JOIN aoi a ON ST_Intersects(a.geom, fh.geom)
            WHERE a.id = $1 AND fh.acq_date >= $3 AND fh.detection_type = 0
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
        post_fire = load_regional_thresholds().post_fire
        # La stessa finestra che neutralizza il fattore piu' sotto, qui usata
        # per non leggere nemmeno: 30,44 giorni e' il mese medio, coerente col
        # `/30` con cui i mesi si ricavano subito dopo.
        oldest = ctx.valuation_time.date() - timedelta(days=post_fire.window_months_max * 30.44)
        async with acquire() as conn:
            row = await conn.fetchrow(_QUERY_SQL, ctx.aoi_id, self._min_hotspots, oldest)

        last_fire = row["last_fire"] if row else None
        if last_fire is None:
            log.info("executor.fire_check", aoi_id=ctx.aoi_id, months_since_fire=None)
            return ctx.with_update(months_since_fire=None)

        delta_days = (ctx.valuation_time.date() - last_fire).days
        months = max(0.0, delta_days / 30.0)
        if months > post_fire.window_months_max:
            # Out of the amplification window — record but neutralise.
            log.info(
                "executor.fire_check.window_expired",
                aoi_id=ctx.aoi_id,
                months_since_fire=months,
                window_max=post_fire.window_months_max,
            )
            return ctx.with_update(months_since_fire=None)

        density = await perimeter_severity_at(ctx.aoi_id, on_or_before=last_fire)
        severity = frp_severity(density, post_fire=post_fire)

        log.info(
            "executor.fire_check",
            aoi_id=ctx.aoi_id,
            months_since_fire=months,
            last_fire=str(last_fire),
            frp_density=density,
            fire_severity=severity,
        )
        return ctx.with_update(months_since_fire=months, fire_severity=severity)
