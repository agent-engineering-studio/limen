"""L'FWI ufficiale di EFFIS dal suo WMS, come numeri e non come colori (#280).

EFFIS pubblica la catena FWI calcolata sul meteo di Météo-France sullo stesso
MapServer dei perimetri, ma all'endpoint ``/effis`` e non ``/gwis``. Chiesto
con ``FORMAT=image/tiff`` restituisce un GeoTIFF float32 con i valori grezzi:
lo si campiona sui nodi di Limen e si confronta con ``fwi_state``. Serve solo a
misurare la nostra catena, non entra nel punteggio.

Tre cose verificate dal vivo il 19 ottobre 2026, che la documentazione non
dice o dice sbagliate:

* i layer sono ``mf010.<componente>`` (fwi, ffmc, dmc, dc, isi, bui); il
  ``ecmwf007.fwi`` dell'esempio sulla pagina EFFIS risponde LayerNotDefined;
* ``TIME`` accetta i giorni passati, oggi e i due seguenti; più avanti la
  risposta è 200 con un raster **tutto a zero**, che è l'assenza del dato e
  non un giorno calmo — qui diventa ``None``;
* il mare è zero anche nei giorni validi: un nodo a terra legge il suo
  pixel, e lo zero di un singolo pixel resta un valore.

Pubblico, senza credenziali, CC BY 4.0. Una lettura fallita restituisce
``None`` e lo scrive (`integration.degraded`): è una misura, non una scrittura.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import fetch_with_retry

log = get_logger(__name__)

WMS_URL = "https://maps.effis.emergency.copernicus.eu/effis"
Componente = Literal["fwi", "ffmc", "dmc", "dc", "isi", "bui"]
COMPONENTI: tuple[Componente, ...] = ("fwi", "ffmc", "dmc", "dc", "isi", "bui")

#: Sud, ovest, nord, est: l'Italia, nell'ordine degli assi di EPSG:4326 in WMS 1.3.0.
BBOX_ITALIA = (36.0, 6.0, 47.6, 19.0)
#: Il passo del raster che si chiede: 0,05°, un quinto del passo dei nodi FWI (0,25°).
PASSO = 0.05

Nodo = tuple[float, float]


def parametri(giorno: date, componente: Componente) -> dict[str, str]:
    sud, ovest, nord, est = BBOX_ITALIA
    return {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": f"mf010.{componente}",
        "STYLES": "",
        "CRS": "EPSG:4326",
        "BBOX": f"{sud},{ovest},{nord},{est}",
        "WIDTH": str(round((est - ovest) / PASSO)),
        "HEIGHT": str(round((nord - sud) / PASSO)),
        "FORMAT": "image/tiff",
        "TIME": giorno.isoformat(),
    }


def campiona(tiff: bytes, nodi: list[Nodo]) -> dict[Nodo, float] | None:
    """Il valore del pixel sotto ogni nodo; ``None`` se il raster è vuoto."""
    import numpy as np
    from rasterio.io import MemoryFile

    with MemoryFile(tiff) as mem, mem.open() as raster:
        valori = raster.read(1)
        if not np.any(valori):
            return None
        fuori = raster.height, raster.width
        out: dict[Nodo, float] = {}
        for lon, lat in nodi:
            riga, colonna = raster.index(lon, lat)
            if 0 <= riga < fuori[0] and 0 <= colonna < fuori[1]:
                v = float(valori[riga, colonna])
                if np.isfinite(v):
                    out[(lon, lat)] = v
        return out


async def fwi_ufficiale(
    giorno: date, nodi: list[Nodo], componente: Componente = "fwi"
) -> dict[Nodo, float] | None:
    """Un componente della catena EFFIS per ``giorno``, campionato sui nodi."""
    try:
        risposta = await fetch_with_retry("GET", WMS_URL, params=parametri(giorno, componente))
    except (httpx.HTTPError, RetryError) as exc:
        log.warning(
            "integration.degraded",
            label="effis.fwi",
            giorno=giorno.isoformat(),
            componente=componente,
            error_type=type(exc).__name__,
        )
        return None
    if not risposta.headers.get("content-type", "").startswith("image/tiff"):
        # MapServer risponde 200 anche agli errori, con un XML.
        log.warning(
            "integration.degraded",
            label="effis.fwi",
            giorno=giorno.isoformat(),
            componente=componente,
            content_type=risposta.headers.get("content-type", ""),
        )
        return None
    return campiona(risposta.content, nodi)


__all__ = ["COMPONENTI", "WMS_URL", "Componente", "campiona", "fwi_ufficiale", "parametri"]
