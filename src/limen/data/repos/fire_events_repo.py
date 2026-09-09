"""Eventi incendio per cella-giorno e densità storica (#66).

Tutto set-based: gli hotspot sono ~300.000 righe per l'Italia e le celle
312.000, quindi il raggruppamento e il conteggio si fanno in SQL in una
passata. Portare i punti in Python per raggrupparli sarebbe la versione lenta
della stessa GROUP BY.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

#: VIIRS parte dal 2012 ed è il prodotto a 375 m; MODIS a 1 km sovrastima
#: l'estensione su celle da 1 km². La finestra di default della densità è
#: quindi l'era VIIRS, come chiede la issue — ma il filtro è per *data*, non
#: per sorgente, così includere MODIS resta una scelta del chiamante.
VIIRS_ERA_START = date(2012, 1, 1)

#: Classificazione FIRMS di un incendio di vegetazione. Le altre classi —
#: vulcano, sorgente statica al suolo, offshore — sono detection corrette di
#: cose che non sono incendi.
VEGETATION_FIRE = 0

#: Svuota la finestra prima di ricostruirla. **Due istruzioni separate**, non
#: una CTE `WITH deleted AS (DELETE ...) INSERT`: in PostgreSQL le CTE che
#: modificano dati e la query esterna vedono lo *stesso* snapshot, quindi la
#: DELETE non è visibile alla INSERT e le righe collidono sulla chiave
#: primaria. Provato: `duplicate key value violates fire_events_pkey`.
_CLEAR_EVENTS_SQL = """
DELETE FROM fire_events WHERE event_date >= $1 AND event_date <= $2
"""

#: Ricostruisce `fire_events` per una finestra: una riga per cella-giorno.
#: DELETE + INSERT sulla finestra e non un upsert riga per riga, perché una
#: detection ritirata da un riprocessamento deve poter *sparire*: un upsert
#: lascerebbe l'evento vecchio in tabella per sempre.
#:
#: **Solo `detection_type = 0`.** Senza questo filtro la cella con la densità
#: più alta d'Italia era l'ILVA di Taranto con 3.308 giorni-incendio su ~4.700
#: giorni d'archivio, la seconda un impianto lombardo, e la Sicilia contava
#: l'Etna. Il filtro di confidenza non li toglie e non può: un'acciaieria è
#: una detection ad alta confidenza e alta potenza radiativa, perché è
#: davvero calda.
#:
#: Una detection di classe **ignota** (`NULL`, righe NRT ingerite prima che la
#: colonna venisse letta) non diventa un evento: sbagliare per difetto perde
#: qualche giorno di feed recente, sbagliare per eccesso rimette Taranto nel
#: truth set ogni giorno dell'anno.
_REBUILD_EVENTS_SQL = """
INSERT INTO fire_events (cell_id, event_date, hotspots, sources, max_frp_mw)
SELECT g.id,
       h.acq_date,
       count(*)::int,
       array_agg(DISTINCT h.source ORDER BY h.source),
       max(h.frp_mw)
FROM fire_hotspots h
JOIN grid_cells g ON ST_Intersects(g.geom, h.geom)
WHERE h.acq_date >= $1 AND h.acq_date <= $2
  AND h.detection_type = $3
GROUP BY g.id, h.acq_date
"""

#: Densità = giorni-incendio distinti per cella nella finestra. Le celle sono
#: di 1 km², quindi il conteggio è già la densità per km².
_FIRE_DENSITY_SQL = """
WITH counts AS (
    SELECT g.id AS cell_id,
           count(e.event_date)::int AS days
    FROM grid_cells g
    LEFT JOIN fire_events e
           ON e.cell_id = g.id
          AND e.event_date >= $2
          AND e.event_date <= $3
    WHERE g.aoi_id = $1
    GROUP BY g.id
)
UPDATE cell_static_factors c
SET fire_density = counts.days,
    updated_at = now()
FROM counts
WHERE c.cell_id = counts.cell_id
"""


@dataclass(frozen=True, slots=True)
class FireEvent:
    cell_id: str
    event_date: date
    hotspots: int
    sources: tuple[str, ...]
    max_frp_mw: float | None


async def rebuild_events(*, start: date, end: date, timeout: float | None = None) -> int:
    """Ricostruisce gli eventi nella finestra. Ritorna le righe scritte."""
    async with acquire() as conn, conn.transaction():
        await conn.execute(_CLEAR_EVENTS_SQL, start, end, timeout=timeout)
        status = await conn.execute(
            _REBUILD_EVENTS_SQL, start, end, VEGETATION_FIRE, timeout=timeout
        )
    written = int(status.split()[-1]) if status else 0
    log.info("fire_events.rebuilt", start=start.isoformat(), end=end.isoformat(), rows=written)
    return written


async def refresh_density(
    aoi_id: str,
    *,
    start: date = VIIRS_ERA_START,
    end: date | None = None,
    timeout: float | None = None,
) -> None:
    """Riscrive `fire_density` per una AOI. Idempotente."""
    async with acquire() as conn:
        await conn.execute(
            _FIRE_DENSITY_SQL,
            aoi_id,
            start,
            end or date.today(),
            timeout=timeout,
        )


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT count(*)::bigint AS n FROM fire_events")
    return int(row["n"]) if row else 0


async def events_for_cells(aoi_id: str, *, start: date, end: date) -> dict[str, date]:
    """``{cell_id: primo giorno-incendio}`` — il truth set del backtest.

    Il primo evento per cella è l'ancora: una cella bruciata tre volte nella
    finestra è **un** positivo, non tre, altrimenti un'area ben allertata
    gonfierebbe l'hit rate quanto più spesso ha preso fuoco.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.cell_id, min(e.event_date) AS first_day
            FROM fire_events e
            JOIN grid_cells g ON g.id = e.cell_id
            WHERE g.aoi_id = $1
              AND e.event_date >= $2
              AND e.event_date <= $3
            GROUP BY e.cell_id
            """,
            aoi_id,
            start,
            end,
        )
    return {str(r["cell_id"]): r["first_day"] for r in rows}


async def effis_firms_agreement(
    *, start: date, end: date, radius_m: float = 1000.0, day_slack: int = 2
) -> dict[str, int]:
    """Quanti perimetri EFFIS hanno un hotspot FIRMS vicino e in data.

    Il controllo di sanità che la issue chiede: i due dataset sono
    indipendenti, quindi il loro accordo è la migliore prova disponibile che
    l'ingest funzioni. Un accordo basso non significa "un dataset è
    sbagliato": EFFIS mappa i perimetri sopra una soglia di area, FIRMS vede
    anche i roghi piccoli ma perde quelli sotto le nuvole.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            WITH perim AS (
                SELECT id, fire_date, geom
                FROM fire_perimeters
                WHERE fire_date >= $1 AND fire_date <= $2
            )
            SELECT count(*)::int AS perimeters,
                   count(*) FILTER (WHERE EXISTS (
                       SELECT 1 FROM fire_hotspots h
                       WHERE h.acq_date BETWEEN p.fire_date - $4::int
                                            AND p.fire_date + $4::int
                         AND h.detection_type = 0
                         AND ST_DWithin(h.geom::geography, p.geom::geography, $3)
                   ))::int AS matched
            FROM perim p
            """,
            start,
            end,
            radius_m,
            day_slack,
        )
    perimeters = int(row["perimeters"]) if row else 0
    matched = int(row["matched"]) if row else 0
    log.info(
        "fire_history.effis_agreement",
        perimeters=perimeters,
        matched=matched,
        radius_m=radius_m,
        day_slack=day_slack,
    )
    return {"perimeters": perimeters, "matched": matched}


__all__ = [
    "VEGETATION_FIRE",
    "VIIRS_ERA_START",
    "FireEvent",
    "count_events",
    "effis_firms_agreement",
    "events_for_cells",
    "rebuild_events",
    "refresh_density",
]
