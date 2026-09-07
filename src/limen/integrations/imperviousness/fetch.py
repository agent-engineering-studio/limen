"""Scarica il raster CLMS Imperviousness Density dal servizio pubblico EEA.

Il dataset è l'HRL Imperviousness Density 2018 di Copernicus Land — lo stesso
prodotto che ``land.copernicus.eu`` distribuisce dietro registrazione. Non
serve un account: l'EEA lo pubblica su un ImageServer aperto, e ``exportImage``
restituisce GeoTIFF georeferenziati.

È la stessa lezione di EFFIS: una sorgente che sembra chiusa può essere
pubblica da un altro endpoint, e vale la pena verificarlo prima di dichiarare
un layer non ottenibile.

Tre scelte che il resto del modulo dà per fatte:

* **EPSG:3035**, non il 3857 del servizio. È il CRS metrico del progetto, i
  pixel sono equivalenti in area a ogni latitudine, e il bbox viene agganciato
  a una griglia di 100 m così la risoluzione è esattamente quella dichiarata.
* **Nearest neighbour**, mai bilineare. Il layer porta i sentinella 254
  (non classificabile) e 255 (nessun dato) dentro la stessa banda dei valori
  0-100: un'interpolazione fra 0 e 255 può cadere sotto 100 e diventare un
  "64 % sigillato" indistinguibile dal dato vero, proprio dove il dato manca.
* **Un file o nessuno.** Le tessere vengono scritte in un ``.part`` e
  rinominate solo alla fine: un download interrotto non lascia un raster
  parziale che il bootstrap leggerebbe come completo.
"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

#: ImageServer pubblico dell'EEA. Il layer è tematico, 1 banda, uint8.
CLMS_IMD_2018_URL = (
    "https://image.discomap.eea.europa.eu/arcgis/rest/services/GioLandPublic/"
    "HRL_ImperviousnessDensity_2018/ImageServer/exportImage"
)

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

_TARGET_EPSG = 3035
_CONCURRENCY = 3
_REQUEST_TIMEOUT_S = 180.0


@dataclass(frozen=True, slots=True)
class Tile:
    """Una richiesta: la finestra in pixel sul raster di destinazione."""

    col_off: int
    row_off: int
    width: int
    height: int

    def bounds(
        self, *, origin_x: float, origin_y: float, res: float
    ) -> tuple[float, float, float, float]:
        """Bbox in EPSG:3035. L'origine è l'angolo in alto a sinistra."""
        x0 = origin_x + self.col_off * res
        y1 = origin_y - self.row_off * res
        return (x0, y1 - self.height * res, x0 + self.width * res, y1)


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


def snap_bounds(
    bounds_4326: tuple[float, float, float, float], *, res: float = RESOLUTION_M
) -> tuple[float, float, float, float]:
    """Riproietta in 3035 e allarga fino al multiplo di ``res``.

    Allargare e non arrotondare: un bordo tagliato a metà pixel darebbe
    risoluzione non intera e costringerebbe il servizio a ricampionare per
    farci stare la dimensione richiesta.
    """
    from pyproj import Transformer

    lon0, lat0, lon1, lat1 = bounds_4326
    t = Transformer.from_crs(4326, _TARGET_EPSG, always_xy=True)
    # I quattro angoli, non due: la proiezione curva i lati, e prendere solo
    # gli estremi opposti perderebbe una striscia lungo il bordo nord o sud.
    xs, ys = zip(
        *[t.transform(lon, lat) for lon in (lon0, lon1) for lat in (lat0, lat1)],
        strict=True,
    )
    return (
        math.floor(min(xs) / res) * res,
        math.floor(min(ys) / res) * res,
        math.ceil(max(xs) / res) * res,
        math.ceil(max(ys) / res) * res,
    )


def plan_tiles(width: int, height: int, *, tile_px: int = TILE_PX) -> list[Tile]:
    """Copre il raster con finestre allineate ai pixel di destinazione.

    Allineate per costruzione: una tessera inserita in una finestra che non
    cade su un confine di pixel andrebbe ricampionata in scrittura, e ogni
    ricampionamento su una banda con sentinella può inventare valori validi.
    """
    return [
        Tile(
            col_off=col,
            row_off=row,
            width=min(tile_px, width - col),
            height=min(tile_px, height - row),
        )
        for row in range(0, height, tile_px)
        for col in range(0, width, tile_px)
    ]


async def _fetch_tile(tile: Tile, *, bounds: tuple[float, ...], url: str) -> bytes:
    from limen.integrations._http import fetch_with_retry

    params = {
        "bbox": ",".join(f"{v:.1f}" for v in bounds),
        "bboxSR": str(_TARGET_EPSG),
        "imageSR": str(_TARGET_EPSG),
        "size": f"{tile.width},{tile.height}",
        "format": "tiff",
        "pixelType": "U8",
        "interpolation": "RSP_NearestNeighbor",
        "f": "image",
    }
    resp = await fetch_with_retry("GET", url, params=params, timeout=_REQUEST_TIMEOUT_S)
    # Un ImageServer risponde all'errore con un JSON e status 200: senza
    # questo controllo il JSON finirebbe in rasterio come "TIFF corrotto",
    # nascondendo il messaggio che dice cosa non è piaciuto della richiesta.
    ctype = resp.headers.get("content-type", "")
    if "json" in ctype:
        raise RuntimeError(f"exportImage ha risposto con un errore: {resp.text[:300]}")
    return resp.content


def _paste(dst: Any, data: bytes, tile: Tile) -> int:
    """Scrive la tessera nella sua finestra. Ritorna i pixel validi (0-100)."""
    import numpy as np
    from rasterio.io import MemoryFile
    from rasterio.windows import Window

    with MemoryFile(data) as mem, mem.open() as src:
        band = src.read(1)
    if band.shape != (tile.height, tile.width):
        raise RuntimeError(
            f"exportImage ha restituito {band.shape[1]}x{band.shape[0]} "
            f"invece di {tile.width}x{tile.height}: la tessera non combacia "
            f"con la finestra e incollarla sposterebbe i dati"
        )
    if band.dtype != np.uint8:
        band = band.astype(np.uint8, copy=False)
    dst.write(
        band,
        window=Window(tile.col_off, tile.row_off, tile.width, tile.height),
        indexes=1,
    )
    return int(np.count_nonzero(band <= 100))


def _resolve_dest(dest: Path | str | None) -> Path:
    if dest is not None:
        return Path(dest)
    env_value = os.environ.get(DEST_ENV)
    return Path(env_value) if env_value else DEFAULT_DEST


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

    x0, y0, x1, y1 = snap_bounds(box)
    width = round((x1 - x0) / RESOLUTION_M)
    height = round((y1 - y0) / RESOLUTION_M)
    tiles = plan_tiles(width, height, tile_px=tile_px)
    log.info(
        "imperviousness.fetch.start",
        width=width,
        height=height,
        tiles=len(tiles),
        bounds_3035=[x0, y0, x1, y1],
        dest=str(target),
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    valid = 0
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def _one(tile: Tile) -> tuple[Tile, bytes]:
        async with gate:
            data = await _fetch_tile(
                tile,
                bounds=tile.bounds(origin_x=x0, origin_y=y1, res=RESOLUTION_M),
                url=url,
            )
        return tile, data

    try:
        valid = await _write_mosaic(
            partial,
            tiles=tiles,
            fetch_one=_one,
            width=width,
            height=height,
            origin=(x0, y1),
        )
    except BaseException:
        # Un `.part` sopravvissuto verrebbe riprovato al giro dopo come se
        # fosse un file valido a metà: meglio niente che un raster bugiardo.
        partial.unlink(missing_ok=True)
        raise

    partial.replace(target)
    log.info(
        "imperviousness.fetch.done",
        path=str(target),
        size_mb=round(target.stat().st_size / 1e6, 1),
        valid_px=valid,
        valid_fraction=round(valid / (width * height), 3),
    )
    return target


async def _write_mosaic(
    partial: Path,
    *,
    tiles: list[Tile],
    fetch_one: Callable[[Tile], Awaitable[tuple[Tile, bytes]]],
    width: int,
    height: int,
    origin: tuple[float, float],
) -> int:
    """Crea il GeoTIFF e incolla ogni tessera appena arriva.

    Non pre-riempie di nodata: ``plan_tiles`` partiziona esattamente il
    raster, quindi ogni pixel viene scritto una volta e una sola. Se una
    tessera manca il file non viene rinominato, quindi nessuno lo legge.
    """
    import rasterio
    from rasterio.transform import from_origin

    valid = 0
    with rasterio.open(
        partial,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs=f"EPSG:{_TARGET_EPSG}",
        transform=from_origin(origin[0], origin[1], RESOLUTION_M, RESOLUTION_M),
        nodata=NODATA,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    ) as dst:
        for done, coro in enumerate(asyncio.as_completed([fetch_one(t) for t in tiles]), 1):
            tile, data = await coro
            valid += _paste(dst, data, tile)
            log.info("imperviousness.fetch.tile", done=done, total=len(tiles))
    return valid


__all__ = [
    "CLMS_IMD_2018_URL",
    "DEFAULT_DEST",
    "DEST_ENV",
    "IMPERVIOUSNESS_FORCE_ENV",
    "NODATA",
    "RESOLUTION_M",
    "Tile",
    "aoi_bounds_4326",
    "fetch_imperviousness",
    "plan_tiles",
    "snap_bounds",
]
