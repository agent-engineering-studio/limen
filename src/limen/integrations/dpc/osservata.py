"""Le letture del radar sulle celle per il ramo pluviale dell'alluvione (#643).

Tre usi della libreria ``dpc-radar``, ognuno acceso da un blocco di
``pluvial.observed`` in ``flood.yaml`` e spento finché non è misurato:

* ``affidabilita``: quanto vede il radar sulla cella (``reliability``);
* ``ritorno``: ogni quanti anni capita lì la cumulata osservata
  (``return_period``, climatologia del solo radar 2018-2025);
* ``nowcast``: i mm dei prossimi minuti dal radar spostato lungo il suo moto
  (``rain_ahead``, dagli SRI dell'ultima mezz'ora).

Ogni regione chiede lo stesso fotogramma nazionale: il calcolo sull'intera
griglia si fa una volta per fotogramma e si tiene finché ne arriva un altro.
Il nowcast degrada a ``None`` (nessuna cella), mai a zero.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from dpc_radar import DpcRadarError, Forecast, RainGrid, rain_ahead, reliability_map, return_period
from rasterio.errors import RasterioError

from limen.core.logging import get_logger
from limen.integrations.dpc.client import get_sri_series

log = get_logger(__name__)

#: Gli SRI per il moto: il più vecchio entro 30 minuti, due vicini entro 15
#: (``MAX_BASELINE`` e ``MAX_STEP`` di dpc-radar).
_PASSO_SRI = timedelta(minutes=15)
_FOTOGRAMMI_SRI = 3

_campi: dict[tuple[str, str, datetime], RainGrid] = {}
_previsto: dict[tuple[datetime, int], Forecast] = {}


def _campo(nome: str, grid: RainGrid) -> RainGrid:
    chiave = (nome, grid.product.name, grid.time)
    if chiave not in _campi:
        dati = reliability_map().like(grid) if nome == "affidabilita" else return_period(grid)
        if len(_campi) > 4:  # due campi per i fotogrammi di adesso, gli altri sono vecchi
            _campi.clear()
        _campi[chiave] = replace(grid, data=dati)
    return _campi[chiave]


def _letto(
    nome: str, grid: RainGrid, punti: list[tuple[float, float]]
) -> list[float | None] | None:
    try:
        return _campo(nome, grid).sample(punti)
    except (DpcRadarError, ValueError, OSError, RasterioError) as exc:
        log.warning("integration.degraded", source=f"dpc_{nome}", error=str(exc))
        return None


def affidabilita(grid: RainGrid, punti: list[tuple[float, float]]) -> list[float | None] | None:
    """Il punteggio di affidabilità del radar (0-1) su ogni punto; ``None`` se non si legge."""
    return _letto("affidabilita", grid, punti)


def ritorno(grid: RainGrid, punti: list[tuple[float, float]]) -> list[float | None] | None:
    """Il tempo di ritorno (anni, tetto 50) su ogni punto; ``None`` se non si legge."""
    return _letto("ritorno", grid, punti)


async def nowcast(
    minuti: int, punti: list[tuple[float, float]], *, adesso: datetime, eta_massima: timedelta
) -> list[float | None] | None:
    """I mm dei prossimi ``minuti`` su ogni punto; ``None`` se il nowcast non si può fare."""
    serie = await get_sri_series(_PASSO_SRI, _FOTOGRAMMI_SRI)
    if len(serie) < 2 or abs(adesso - serie[-1].time) > eta_massima:
        return None
    chiave = (serie[-1].time, minuti)
    if chiave not in _previsto:
        try:
            _previsto.clear()
            _previsto[chiave] = rain_ahead(serie, minutes=minuti)
        except (DpcRadarError, ValueError, RasterioError) as exc:
            log.warning("integration.degraded", source="dpc_nowcast", error=str(exc))
            return None
    return _previsto[chiave].sample(punti)
