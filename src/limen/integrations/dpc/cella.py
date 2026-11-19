"""Il radar visto da una cella: quanto ci si può fidare, e quanto è rara la pioggia caduta (#643).

Due letture della libreria ``dpc-radar``, tutte e due mappe statiche nel
pacchetto, senza rete:

* ``reliability``: quanto vede il radar in quel punto (quota del fascio più
  basso, copertura nei mesi, accordo con il «Merging»). Sotto
  ``RELIABLE_FROM`` uno zero del radar non vuol dire «asciutto»: il caso di
  Lipari del 10/10/2026;
* ``rarity``: ogni quanti anni capita in quel posto la pioggia che il
  «Merging» ha misurato nella finestra dell'alluvione. La climatologia è fatta
  sul solo radar 2018-2025: i millimetri del «Merging» (radar più pluviometri)
  le si confrontano bene dove i due vanno d'accordo, cioè dove ``agreement``
  è alto.

È un'etichetta per il riquadro della cella: non entra nel punteggio.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from dpc_radar import DpcRadarError, rarity, reliability
from dpc_radar.climatology import WINDOWS
from rasterio.errors import RasterioError

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RadarCella:
    #: ``None`` fuori dalla mappa del radar.
    affidabile: bool | None
    punteggio: float | None
    visibilita: float | None
    copertura: float | None
    accordo: float | None
    quota_fascio_m: float | None
    radar_vicino: str
    distanza_km: float
    #: La pioggia già caduta letta dallo sweep, e la sua rarità in quel posto.
    pioggia_mm: float | None
    finestra_ore: int | None
    ritorno_anni: float | None
    ritorno_basso: float | None
    ritorno_alto: float | None
    anni_di_dati: int


def pioggia_osservata(hazard: HazardType, factors: dict[str, Any]) -> tuple[float, int] | None:
    """La pioggia già caduta che lo sweep dell'alluvione ha letto, e la sua finestra in ore."""
    if hazard is not HazardType.FLOOD:
        return None
    t = load_hazard_thresholds(HazardType.FLOOD)
    if not isinstance(t, FloodThresholds) or t.pluvial.observed is None:
        return None
    mm = factors.get("rain_observed_mm")
    if not isinstance(mm, int | float):
        return None
    return float(mm), t.pluvial.observed.hours


def radar_della_cella(
    lon: float, lat: float, hazard: HazardType, factors: dict[str, Any]
) -> RadarCella:
    osservata = pioggia_osservata(hazard, factors)
    pioggia_mm, finestra_ore = osservata if osservata else (None, None)
    r = reliability(lon, lat)
    rara = (
        rarity(finestra_ore, lon, lat, pioggia_mm)
        if pioggia_mm is not None and pioggia_mm > 0 and finestra_ore in WINDOWS
        else None
    )
    return RadarCella(
        affidabile=r.reliable,
        punteggio=r.score,
        visibilita=r.visibility,
        copertura=r.coverage,
        accordo=r.agreement,
        quota_fascio_m=r.beam_height,
        radar_vicino=r.nearest_site,
        distanza_km=round(r.distance_km, 1),
        pioggia_mm=pioggia_mm,
        finestra_ore=finestra_ore if rara is not None else None,
        ritorno_anni=rara.return_period if rara else None,
        ritorno_basso=rara.low if rara else None,
        ritorno_alto=rara.high if rara else None,
        anni_di_dati=rara.years if rara else 0,
    )


async def radar_per_cella(
    cell_id: str, hazard: HazardType, factors: dict[str, Any]
) -> RadarCella | None:
    """Per l'API: ``None`` se la cella non c'è o le mappe non si leggono.

    Un'etichetta che manca non deve trascinare con sé il riquadro della cella;
    le mappe del pacchetto si leggono fuori dal loop (la prima volta da disco).
    """
    from limen.data.repos import grid_repo

    punto = await grid_repo.centroide(cell_id)
    if punto is None:
        return None
    try:
        return await asyncio.to_thread(radar_della_cella, *punto, hazard, factors)
    except (DpcRadarError, ValueError, OSError, RasterioError) as exc:
        log.warning("integration.degraded", source="dpc_radar_cella", error=str(exc))
        return None
