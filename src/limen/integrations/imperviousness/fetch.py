"""Scarica il raster CLMS Imperviousness Density dal servizio pubblico EEA.

Il dataset è l'HRL Imperviousness Density 2018 di Copernicus Land — lo stesso
prodotto che ``land.copernicus.eu`` distribuisce dietro registrazione. Non
serve un account: l'EEA lo pubblica su un ImageServer aperto, e ``exportImage``
restituisce GeoTIFF georeferenziati.

È la stessa lezione di EFFIS: una sorgente che sembra chiusa può essere
pubblica da un altro endpoint, e vale la pena verificarlo prima di dichiarare
un layer non ottenibile.

Griglia, tessere, richieste e mosaico vengono dal pacchetto
``imageserver-export`` (estratto da qui, Apache-2.0), con le stesse tre scelte
di prima:

* **EPSG:3035**, non il 3857 del servizio: il CRS metrico del progetto, con il
  riquadro agganciato a una griglia di 100 m.
* **Nearest neighbour**, mai bilineare: i sentinella 254 (non classificabile)
  e 255 (nessun dato) stanno nella stessa banda dei valori 0-100, e
  un'interpolazione fra 0 e 255 inventerebbe un «64 % sigillato».
* **Un file o nessuno**: il mosaico si scrive in un ``.part`` e si rinomina
  solo alla fine.

Le richieste passano da ``fetch_with_retry`` (l'aggancio ``send`` della
libreria), come ogni chiamata esterna.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
from imageserver_export import Grid, ImageServer, eea

from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations._http import fetch_with_retry

log = get_logger(__name__)

#: ImageServer pubblico dell'EEA. Il layer è tematico, 1 banda, uint8.
CLMS_IMD_2018_URL = eea("HRL_ImperviousnessDensity_2018")

DEST_ENV = "LIMEN_IMPERVIOUSNESS_DEST"
IMPERVIOUSNESS_FORCE_ENV = "LIMEN_IMPERVIOUSNESS_FORCE"
DEFAULT_DEST = Path("data/sealing/clms_imd_2018/imd_2018_100m.tif")

#: Risoluzione di lavoro. Il nativo è 10 m, ma le celle sono da 1 km: a 100 m
#: ogni cella conserva ~100 pixel, abbastanza per una media stabile, e il
#: raster nazionale sta in poche decine di MB invece di qualche centinaio.
RESOLUTION_M = 100.0

#: Lato della tessera in pixel. Il servizio accetta al massimo 4100 px di
#: altezza; 2048 sta largo sotto il limite e tiene ogni richiesta a pochi MB,
#: così un errore di rete costa una tessera e non l'intero scaricamento.
TILE_PX = 2048

#: Il sentinella "nessun dato" del prodotto. Diventa anche il nodata del
#: raster scritto, così le aree fuori copertura non si confondono con zero
#: sigillato — che affermerebbe suolo permeabile dove non si sa.
NODATA = 255

_CONCURRENCY = 3


async def aoi_bounds_4326() -> tuple[float, float, float, float] | None:
    """Riquadro che contiene tutte le AOI seminate, in gradi.

    Dal database e non da una costante: il riempimento italiano è un caso
    d'uso, non il prodotto. Un clone che semina la Francia scarica la Francia
    senza toccare il codice.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ST_XMin(e) AS x0, ST_YMin(e) AS y0, ST_XMax(e) AS x1, ST_YMax(e) AS y1 "
            "FROM (SELECT ST_Extent(geom) AS e FROM aoi) s"
        )
    if row is None or row["x0"] is None:
        return None
    return (float(row["x0"]), float(row["y0"]), float(row["x1"]), float(row["y1"]))


def _resolve_dest(dest: Path | str | None) -> Path:
    if dest is not None:
        return Path(dest)
    env_value = os.environ.get(DEST_ENV)
    if env_value:
        return Path(env_value)
    # Sotto la radice dati del deployment (#302).
    return radice_dati() / DEFAULT_DEST.relative_to("data")


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    return await fetch_with_retry(method, url, **kwargs)


async def fetch_imperviousness(
    *,
    dest: Path | str | None = None,
    bounds_4326: tuple[float, float, float, float] | None = None,
    url: str = CLMS_IMD_2018_URL,
    tile_px: int = TILE_PX,
    force: bool = False,
) -> Path | None:
    """Scarica il mosaico e scrivilo in ``dest``. ``None`` se non c'è nulla da fare.

    Sicuro da rieseguire: con il file già presente non scarica niente a meno
    di ``force``.
    """
    target = _resolve_dest(dest)
    if target.exists() and not force:
        log.info("imperviousness.fetch.skip", reason="destination exists", path=str(target))
        return target

    box = bounds_4326 or await aoi_bounds_4326()
    if box is None:
        log.warning("imperviousness.fetch.skip", reason="no seeded AOI to cover")
        return None

    grid = Grid.from_lonlat(box, res=RESOLUTION_M, crs=3035)
    log.info(
        "imperviousness.fetch.start",
        width=grid.width,
        height=grid.height,
        bounds_3035=list(grid.bounds),
        dest=str(target),
    )

    def _avanzamento(done: int, total: int) -> None:
        log.info("imperviousness.fetch.tile", done=done, total=total)

    server = ImageServer(url, send=_send)
    result = await server.export(
        grid,
        target,
        nodata=NODATA,
        valid_range=(0, 100),
        tile_px=tile_px,
        concurrency=_CONCURRENCY,
        on_tile=_avanzamento,
    )
    log.info(
        "imperviousness.fetch.done",
        path=str(target),
        size_mb=round(target.stat().st_size / 1e6, 1),
        valid_px=result.valid_px,
        valid_fraction=round(result.valid_fraction, 3),
    )
    return target


__all__ = [
    "CLMS_IMD_2018_URL",
    "DEFAULT_DEST",
    "DEST_ENV",
    "IMPERVIOUSNESS_FORCE_ENV",
    "NODATA",
    "RESOLUTION_M",
    "aoi_bounds_4326",
    "fetch_imperviousness",
]
