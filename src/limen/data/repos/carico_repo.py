"""Il carico per pericolo: ``carico.sql`` sul database (#345).

La quota di comuni-giorno con una previsione ≥ Moderato, da leggere accanto
alla quota di eventi colti di ``limen verifiche-report``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from importlib import resources

from limen.api.jobs.ids import JOB_FORECAST_HISTORY
from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.anticipo_repo import ATTESA_S

#: Il carico legge tutto lo storico previsionale (9,5 milioni di righe al
#: 20/11/2026): 157 s a database scarico, oltre i 180 s di ``ATTESA_S`` con un
#: backtest che gira. È un report a mano, non la mappa.
ATTESA_CARICO_S = 900.0


@dataclass(frozen=True, slots=True)
class Carico:
    hazard: HazardType
    #: Comuni-giorno con almeno una cella prevista ≥ Moderato.
    comuni_giorno_sopra: int
    comuni: int
    #: Giorni che una corsa previsionale ha guardato.
    giorni: int
    dal_giorno: date
    al_giorno: date

    @property
    def quota(self) -> float | None:
        """``None`` senza comuni-giorno valutati: non misurato non è zero."""
        totale = self.comuni * self.giorni
        return self.comuni_giorno_sopra / totale if totale else None


@cache
def _sql(nome: str = "carico.sql") -> str:
    return resources.files(__package__).joinpath(nome).read_text(encoding="utf-8")


async def misura(*, dal: datetime | None, al: datetime | None) -> dict[HazardType, Carico]:
    """Un pericolo senza giorni valutati nella finestra non c'è nel risultato."""
    async with acquire() as conn:
        rows = await conn.fetch(_sql(), dal, al, JOB_FORECAST_HISTORY, timeout=ATTESA_CARICO_S)
    return {
        HazardType(r["hazard"]): Carico(
            hazard=HazardType(r["hazard"]),
            comuni_giorno_sopra=int(r["comuni_giorno_sopra"]),
            comuni=int(r["comuni"]),
            giorni=int(r["giorni"]),
            dal_giorno=r["dal_giorno"],
            al_giorno=r["al_giorno"],
        )
        for r in rows
    }


async def centroidi() -> list[tuple[str, float, float]]:
    """``(cella, lon, lat)`` di ogni cella della griglia."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, ST_X(centroid) AS lon, ST_Y(centroid) AS lat FROM grid_cells",
            timeout=ATTESA_S,
        )
    return [(r["id"], float(r["lon"]), float(r["lat"])) for r in rows]


async def classi_previste(
    giorno: date, prima_di: datetime, pericoli: list[HazardType]
) -> dict[str, dict[HazardType, list[str]]] | None:
    """Le classi ≥ Moderato previste per ``giorno`` dalle corse partite prima di ``prima_di``.

    ``cella → pericolo → classi``; una cella assente era prevista sotto
    Moderato. ``None`` se in quelle 72 ore nessuna corsa previsionale è
    riuscita: senza previsione il giorno non è calmo, è non valutato.
    """
    async with acquire() as conn:
        corse = await conn.fetchval(
            "SELECT count(*) FROM job_runs WHERE job_id = $1 AND status = 'ok' "
            "AND started_at >= $2 AND started_at < $3",
            JOB_FORECAST_HISTORY,
            datetime.combine(giorno - timedelta(days=3), time(), UTC),
            prima_di,
            timeout=ATTESA_S,
        )
        if not corse:
            return None
        rows = await conn.fetch(
            _sql("classi_previste.sql"),
            giorno,
            prima_di,
            [p.value for p in pericoli],
            timeout=ATTESA_S,
        )
    out: dict[str, dict[HazardType, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        out[r["cell_id"]][HazardType(r["hazard"])].append(r["class"])
    return out
