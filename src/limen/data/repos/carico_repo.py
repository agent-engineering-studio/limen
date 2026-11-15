"""Il carico per pericolo: ``carico.sql`` sul database (#345).

La quota di comuni-giorno con una previsione ≥ Moderato, da leggere accanto
alla quota di eventi colti di ``limen verifiche-report``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from functools import cache
from importlib import resources

from limen.api.jobs.ids import JOB_FORECAST_HISTORY
from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.anticipo_repo import ATTESA_S


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
def _sql() -> str:
    return resources.files(__package__).joinpath("carico.sql").read_text(encoding="utf-8")


async def misura(*, dal: datetime | None, al: datetime | None) -> dict[HazardType, Carico]:
    """Un pericolo senza giorni valutati nella finestra non c'è nel risultato."""
    async with acquire() as conn:
        rows = await conn.fetch(_sql(), dal, al, JOB_FORECAST_HISTORY, timeout=ATTESA_S)
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
