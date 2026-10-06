"""Burnt areas → months_since_fire, **per cell** (#146).

The engine's post-fire window is a Gaussian centred at 6 months. Each cell
gets the most recent fire that **touches that cell**; a cell no fire touched
in the window gets nothing, and the engine then returns 0 for the F component
and 1 for the flood cascade, which is the correct neutral.

Fino alla #146 il valore era uno per AOI — l'incendio più recente della
regione — copiato su ogni cella: un incendio sul Carso dava la spinta
post-incendio al centro di Trieste, e il quadro nazionale contava come
«bruciato» il 99 % d'Italia. Il riepilogo per AOI resta nel contesto, per i
log, ma il punteggio legge `fuoco_per_cella`.

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
WITH perimetri AS (
    -- Il perimetro EFFIS più recente che interseca la cella, con la sua
    -- severità: quella del **suo** incendio, non dell'ultimo della regione.
    SELECT DISTINCT ON (g.id)
           g.id AS cell_id, fp.fire_date AS data, fp.frp_density_mw_per_ha AS densita
    FROM fire_perimeters fp
    JOIN grid_cells g ON g.aoi_id = $1 AND ST_Intersects(g.geom, fp.geom)
    WHERE fp.fire_date >= $3 AND fp.fire_date <= $4
    ORDER BY g.id, fp.fire_date DESC
),
giorni AS (
    -- Un giorno di fuoco è confermato quando la regione ha almeno
    -- `min_hotspots` rilevazioni: un punto solo può essere un riflesso.
    SELECT fh.acq_date
    FROM fire_hotspots fh
    JOIN aoi a ON ST_Intersects(a.geom, fh.geom)
    WHERE a.id = $1 AND fh.acq_date >= $3 AND fh.acq_date <= $4 AND fh.detection_type = 0
    GROUP BY fh.acq_date
    HAVING COUNT(*) >= $2
),
punti AS (
    -- E tocca le sole celle in cui sono cadute le rilevazioni di quel giorno.
    SELECT g.id AS cell_id, MAX(fh.acq_date) AS data
    FROM fire_hotspots fh
    JOIN giorni d ON d.acq_date = fh.acq_date
    JOIN grid_cells g ON g.aoi_id = $1 AND ST_Intersects(g.geom, fh.geom)
    WHERE fh.detection_type = 0
    GROUP BY g.id
)
SELECT COALESCE(p.cell_id, h.cell_id) AS cell_id,
       p.data AS data_perimetro,
       p.densita,
       h.data AS data_punti
FROM perimetri p
FULL JOIN punti h ON h.cell_id = p.cell_id
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
        oggi = ctx.valuation_time.date()
        # La stessa finestra che neutralizza il fattore, qui usata per non
        # leggere nemmeno: 30,44 giorni è il mese medio, coerente col `/30`
        # con cui i mesi si ricavano subito dopo.
        oldest = oggi - timedelta(days=post_fire.window_months_max * 30.44)
        async with acquire() as conn:
            rows = await conn.fetch(_QUERY_SQL, ctx.aoi_id, self._min_hotspots, oldest, oggi)

        per_cella: dict[str, tuple[float, float | None]] = {}
        for r in rows:
            date_note = [d for d in (r["data_perimetro"], r["data_punti"]) if d is not None]
            ultima = max(date_note)
            mesi = max(0.0, (oggi - ultima).days / 30.0)
            if mesi > post_fire.window_months_max:
                continue
            # La severità esiste solo per il perimetro, e solo se è lui
            # l'incendio più recente della cella: un fuoco FIRMS più nuovo su
            # un vecchio perimetro non ha un'area su cui dividere.
            densita = r["densita"] if r["data_perimetro"] == ultima else None
            per_cella[r["cell_id"]] = (
                mesi,
                frp_severity(densita, post_fire=post_fire) if densita is not None else None,
            )

        if not per_cella:
            log.info("executor.fire_check", aoi_id=ctx.aoi_id, months_since_fire=None, cells=0)
            return ctx.with_update(months_since_fire=None, fire_severity=None, fuoco_per_cella={})

        recente = min(per_cella.values(), key=lambda v: v[0])
        log.info(
            "executor.fire_check",
            aoi_id=ctx.aoi_id,
            months_since_fire=recente[0],
            fire_severity=recente[1],
            cells=len(per_cella),
        )
        return ctx.with_update(
            months_since_fire=recente[0], fire_severity=recente[1], fuoco_per_cella=per_cella
        )
