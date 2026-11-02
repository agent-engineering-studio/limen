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

Richiesta e campionamento vengono dal pacchetto ``effis-client``; qui resta
la politica di Limen: il retry condiviso e il degrado neutro.

Pubblico, senza credenziali, CC BY 4.0. Una lettura fallita restituisce
``None`` e lo scrive (`integration.degraded`): è una misura, non una scrittura.
"""

from __future__ import annotations

from datetime import date

import httpx
from effis_client import (
    COMPONENTS,
    WMS_URL,
    Component,
    EffisError,
    check_tiff,
    fwi_params,
    sample_fwi,
)
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import fetch_with_retry

log = get_logger(__name__)

Componente = Component
COMPONENTI = COMPONENTS

#: Ovest, sud, est, nord: l'Italia. Lo scambio degli assi che WMS 1.3.0 vuole
#: in EPSG:4326 lo fa ``fwi_params``.
BBOX_ITALIA = (6.0, 36.0, 19.0, 47.6)
#: Il passo del raster che si chiede: 0,05°, un quinto del passo dei nodi FWI (0,25°).
PASSO = 0.05

Nodo = tuple[float, float]


def parametri(giorno: date, componente: Componente) -> dict[str, str]:
    return fwi_params(giorno, BBOX_ITALIA, component=componente, step=PASSO)


async def fwi_ufficiale(
    giorno: date, nodi: list[Nodo], componente: Componente = "fwi"
) -> dict[Nodo, float] | None:
    """Un componente della catena EFFIS per ``giorno``, campionato sui nodi."""
    from rasterio.errors import RasterioError

    try:
        risposta = await fetch_with_retry("GET", WMS_URL, params=parametri(giorno, componente))
        tiff = check_tiff(risposta.headers.get("content-type", ""), risposta.content)
        # Un corpo dichiarato image/tiff ma troncato passa il controllo
        # dell'intestazione e si rompe solo all'apertura.
        return sample_fwi(tiff, nodi)
    except (httpx.HTTPError, RetryError, EffisError, RasterioError) as exc:
        # MapServer risponde 200 anche agli errori, con un XML: è l'EffisError.
        log.warning(
            "integration.degraded",
            label="effis.fwi",
            giorno=giorno.isoformat(),
            componente=componente,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None


__all__ = ["COMPONENTI", "WMS_URL", "Componente", "fwi_ufficiale", "parametri"]
