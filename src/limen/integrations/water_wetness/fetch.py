"""Scarica l'HRL WaterWetness 2018 dal servizio pubblico EEA (#420).

Stesso servizio e stesse scelte dell'impermeabilizzazione (``imperviousness/
fetch.py``): ImageServer aperto, EPSG:3035, nearest neighbour, un file o
nessuno, tessere riprese dopo un'interruzione. Cambia la risoluzione: **50 m**
invece di 100, perché le classi temporanee seguono greti e golene larghi poche
decine di metri, e a 100 m il campionamento ne perderebbe una parte. Una cella
da 1 km conserva ~400 pixel; l'Italia intera pesa ~6,5 MB.

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
from limen.integrations._http import fetch_with_retry
from limen.integrations.imperviousness.fetch import aoi_bounds_4326

log = get_logger(__name__)

#: ImageServer pubblico dell'EEA. Tematico, 1 banda, uint8: 0 asciutto,
#: 1 acqua permanente, 2 acqua temporanea, 3 umido permanente, 4 umido
#: temporaneo, 253 mare, 254 non classificabile, 255 fuori copertura.
HRL_WW_2018_URL = eea("HRL_WaterWetness_2018")

DEST_ENV = "LIMEN_WATER_WETNESS_DEST"
WATER_WETNESS_FORCE_ENV = "LIMEN_WATER_WETNESS_FORCE"
DEFAULT_DEST = Path("data/water_wetness/hrl_ww_2018/ww_2018_50m.tif")

RESOLUTION_M = 50.0
#: Sotto il limite di 4100 px del servizio, pochi MB a richiesta.
TILE_PX = 2048
NODATA = 255

_CONCURRENCY = 3


def _resolve_dest(dest: Path | str | None) -> Path:
    if dest is not None:
        return Path(dest)
    env_value = os.environ.get(DEST_ENV)
    if env_value:
        return Path(env_value)
    return radice_dati() / DEFAULT_DEST.relative_to("data")


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    return await fetch_with_retry(method, url, **kwargs)


async def fetch_water_wetness(
    *,
    dest: Path | str | None = None,
    bounds_4326: tuple[float, float, float, float] | None = None,
    url: str = HRL_WW_2018_URL,
    tile_px: int = TILE_PX,
    force: bool = False,
) -> Path | None:
    """Scarica il mosaico in ``dest``. ``None`` se non c'è un riquadro da coprire.

    Sicuro da rieseguire: con il file già presente non scarica niente a meno
    di ``force``.
    """
    target = _resolve_dest(dest)
    if target.exists() and not force:
        log.info("water_wetness.fetch.skip", reason="destination exists", path=str(target))
        return target

    box = bounds_4326 or await aoi_bounds_4326()
    if box is None:
        log.warning("water_wetness.fetch.skip", reason="no seeded AOI to cover")
        return None

    grid = Grid.from_lonlat(box, res=RESOLUTION_M, crs=3035)
    log.info(
        "water_wetness.fetch.start",
        width=grid.width,
        height=grid.height,
        bounds_3035=list(grid.bounds),
        dest=str(target),
    )

    def _avanzamento(done: int, total: int) -> None:
        log.info("water_wetness.fetch.tile", done=done, total=total)

    server = ImageServer(url, send=_send)
    result = await server.export(
        grid,
        target,
        nodata=NODATA,
        valid_range=(0, 254),
        tile_px=tile_px,
        concurrency=_CONCURRENCY,
        on_tile=_avanzamento,
        resume=True,
        tags={"limen_layer": "hrl_ww_2018", "limen_resolution_m": f"{RESOLUTION_M:g}"},
    )
    log.info(
        "water_wetness.fetch.done",
        path=str(target),
        size_mb=round(target.stat().st_size / 1e6, 1),
        tiles=result.tiles,
        reused=result.reused,
        valid_px=result.valid_px,
        valid_fraction=round(result.valid_fraction, 3),
    )
    return target


__all__ = [
    "DEFAULT_DEST",
    "DEST_ENV",
    "HRL_WW_2018_URL",
    "NODATA",
    "RESOLUTION_M",
    "WATER_WETNESS_FORCE_ENV",
    "fetch_water_wetness",
]
