"""Le tile del rilievo per la posizione «Rilievo» della mappa (#318).

Il DTM che già dà la pendenza per cella diventa una sorgente ``raster-dem``
di MapLibre: quota codificata in terrain-RGB (la codifica ``mapbox``,
``h = -10000 + (R·65536 + G·256 + B) / 10``), PNG da 256 px in EPSG:3857,
impacchettate in un PMTiles servito come gli altri overlay statici. Niente
tile di terzi a runtime.

Ogni livello di zoom si legge dal DTM attraverso le sue overview, non dalle
tile del livello sotto: la media su una quota codificata in RGB non è una
quota. Il mare (nodata) resta senza tile, e MapLibre lo disegna piatto.

Il comando è idempotente sul costo come il bootstrap statico (#101):
l'impronta della sorgente (percorso, mtime, dimensione), il riquadro, gli
zoom e la versione del codice stanno nei metadati del PMTiles, e un file
con la stessa impronta non si rifà.
"""

from __future__ import annotations

import json
import math
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from limen.core.logging import get_logger

log = get_logger(__name__)

#: Da cambiare quando cambia la codifica o la lettura, non il dato.
VERSIONE = 1
_LATO = 256
_MERCATORE = 20037508.342789244


@dataclass(frozen=True, slots=True)
class Esito:
    percorso: Path
    tile: int
    byte: int
    saltato: bool


def codifica(quota: NDArray[np.floating[Any]]) -> NDArray[np.uint8]:
    """Quote in metri → RGB ``mapbox``, al decimetro."""
    v = np.clip(np.round((quota.astype(np.float64) + 10000.0) * 10.0), 0, 2**24 - 1).astype(
        np.uint32
    )
    return np.stack([(v >> 16) & 255, (v >> 8) & 255, v & 255]).astype(np.uint8)


def decodifica(rgb: NDArray[np.uint8]) -> NDArray[np.float64]:
    r, g, b = (rgb[i].astype(np.float64) for i in range(3))
    return -10000.0 + (r * 65536 + g * 256 + b) / 10.0


def limiti_tile(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """``(minx, miny, maxx, maxy)`` della tile in EPSG:3857."""
    lato = 2 * _MERCATORE / (1 << z)
    minx = -_MERCATORE + x * lato
    maxy = _MERCATORE - y * lato
    return minx, maxy - lato, minx + lato, maxy


def tile_del_riquadro(z: int, riquadro: tuple[float, float, float, float]) -> list[tuple[int, int]]:
    """Le tile ``(x, y)`` di zoom ``z`` che toccano il riquadro lon/lat."""
    lon0, lat0, lon1, lat1 = riquadro
    n = 1 << z

    def x_di(lon: float) -> int:
        return min(n - 1, max(0, math.floor((lon + 180.0) / 360.0 * n)))

    def y_di(lat: float) -> int:
        r = math.radians(lat)
        return min(n - 1, max(0, math.floor((1 - math.asinh(math.tan(r)) / math.pi) / 2 * n)))

    return [
        (x, y) for x in range(x_di(lon0), x_di(lon1) + 1) for y in range(y_di(lat1), y_di(lat0) + 1)
    ]


def impronta(
    sorgente: Path, riquadro: tuple[float, float, float, float], zoom: tuple[int, int]
) -> dict[str, Any]:
    st = sorgente.stat()
    return {
        "sorgente": str(sorgente),
        "mtime_ns": st.st_mtime_ns,
        "dimensione": st.st_size,
        "riquadro": [round(c, 6) for c in riquadro],
        "zoom": list(zoom),
        "versione": VERSIONE,
    }


def _impronta_esistente(percorso: Path) -> dict[str, Any] | None:
    from pmtiles.reader import MmapSource, Reader

    try:
        with percorso.open("rb") as f:
            meta = Reader(MmapSource(f)).metadata()
    except (OSError, ValueError, KeyError):
        return None
    valore = meta.get("limen")
    return valore if isinstance(valore, dict) else None


def _png(rgb: NDArray[np.uint8]) -> bytes:
    from rasterio.errors import NotGeoreferencedWarning
    from rasterio.io import MemoryFile

    # La georeferenza della tile è nel suo z/x/y, non nel PNG.
    with (
        warnings.catch_warnings(category=NotGeoreferencedWarning, action="ignore"),
        MemoryFile() as mem,
        mem.open(driver="PNG", width=_LATO, height=_LATO, count=3, dtype="uint8") as png,
    ):
        png.write(rgb)
        png.close()
        return bytes(mem.read())


def _sorgente_per_zoom(sorgente: Path, z: int) -> Any:
    """Il DTM aperto sull'overview più fine fra quelle non più fini della
    tile: il pixel della tile a zoom ``z`` (in metri veri, alla latitudine
    italiana) diviso il pixel del DTM dice di quanto si può ridurre."""
    import rasterio

    with rasterio.open(sorgente) as src:
        fattori = src.overviews(1)
        pixel = abs(src.res[0])
    pixel_tile = 2 * _MERCATORE / (_LATO * (1 << z)) * math.cos(math.radians(42.0))
    livello = max((i for i, f in enumerate(fattori) if pixel * f <= pixel_tile), default=None)
    if livello is None:
        return rasterio.open(sorgente)
    return rasterio.open(sorgente, overview_level=livello)


def genera(
    sorgente: Path,
    uscita: Path,
    *,
    riquadro: tuple[float, float, float, float],
    zoom: tuple[int, int],
    attribuzione: str,
) -> Esito:
    """Scrive ``uscita`` (atomica: prima un file accanto, poi rinomina)."""
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds
    from rasterio.vrt import WarpedVRT

    voluta = impronta(sorgente, riquadro, zoom)
    if uscita.exists() and _impronta_esistente(uscita) == voluta:
        log.info("dem_tiles.skip", uscita=str(uscita))
        return Esito(uscita, 0, uscita.stat().st_size, saltato=True)

    tile = sorted(
        (zxy_to_tileid(z, x, y), z, x, y)
        for z in range(zoom[0], zoom[1] + 1)
        for x, y in tile_del_riquadro(z, riquadro)
    )
    uscita.parent.mkdir(parents=True, exist_ok=True)
    provvisoria = uscita.with_suffix(".pmtiles.tmp")
    scritte = 0
    with ExitStack() as pila:
        f = pila.enter_context(provvisoria.open("wb"))
        livelli: dict[int, Any] = {}
        writer = Writer(f)
        for tile_id, z, x, y in tile:
            if z not in livelli:
                livelli[z] = pila.enter_context(_sorgente_per_zoom(sorgente, z))
            # Un VRT sulla griglia della tile, letto dall'overview vicina alla
            # risoluzione: dal livello pieno una tile a zoom 5 chiede 50 GB.
            with WarpedVRT(
                livelli[z],
                crs="EPSG:3857",
                transform=from_bounds(*limiti_tile(z, x, y), _LATO, _LATO),
                width=_LATO,
                height=_LATO,
                resampling=Resampling.average,
            ) as vrt:
                quote = vrt.read(1, masked=True)
            if quote.mask.all():
                continue
            writer.write_tile(tile_id, _png(codifica(quote.filled(0.0))))
            scritte += 1
        lon0, lat0, lon1, lat1 = riquadro
        writer.finalize(
            {
                "tile_type": TileType.PNG,
                "tile_compression": Compression.NONE,
                "min_lon_e7": int(lon0 * 1e7),
                "min_lat_e7": int(lat0 * 1e7),
                "max_lon_e7": int(lon1 * 1e7),
                "max_lat_e7": int(lat1 * 1e7),
                "center_zoom": zoom[0],
                "center_lon_e7": int((lon0 + lon1) / 2 * 1e7),
                "center_lat_e7": int((lat0 + lat1) / 2 * 1e7),
            },
            {
                "name": "rilievo",
                "encoding": "mapbox",
                "attribution": attribuzione,
                "limen": voluta,
            },
        )
    provvisoria.replace(uscita)
    log.info("dem_tiles.done", uscita=str(uscita), tile=scritte, byte=uscita.stat().st_size)
    return Esito(uscita, scritte, uscita.stat().st_size, saltato=False)


def riquadro_aoi(aoi_id: str | None) -> tuple[float, float, float, float]:
    """Il riquadro lon/lat di un'AOI regionale del seme, o dell'Italia."""
    from importlib import resources

    from shapely.geometry import shape
    from shapely.ops import unary_union

    seme = json.loads(
        resources.files("limen.data.seed").joinpath("italy_regions_aoi.geojson").read_text()
    )
    geometrie = [
        shape(f["geometry"])
        for f in seme["features"]
        if aoi_id is None or f["properties"]["id"] == aoi_id
    ]
    if not geometrie:
        raise ValueError(f"AOI sconosciuta: {aoi_id}")
    minx, miny, maxx, maxy = unary_union(geometrie).bounds
    return float(minx), float(miny), float(maxx), float(maxy)
