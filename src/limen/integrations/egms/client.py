"""Le tile EGMS Ortho L3 dal portale Copernicus.

Il portale non ha un'API a punti: serve archivi ZIP per tile da 100 km in
EPSG:3035, uno per componente (``U`` verticale, ``E`` est-ovest), come
``EGMS_L3_E47N19_100km_U_2020_2024_1.zip``. Il nome è l'angolo in basso a
sinistra in centinaia di km: E47N19 copre 4.700.000-4.800.000 m est e
1.900.000-2.000.000 m nord. Ogni ZIP (~60 MB) contiene un CSV con le serie
temporali (~245 MB) e un GeoTIFF con la velocità media a 100 m (~4 MB): a
Limen serve solo il secondo, e solo quello si tiene.

Una tile che non esiste (mare, fuori copertura) risponde 404: si lascia un
segnaposto ``.assente`` perché il giro dopo non la richieda. Il token sta
nella query string e non finisce mai in un log.
"""

from __future__ import annotations

import io
import math
import zipfile
from pathlib import Path

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

#: Lato di una tile, in metri EPSG:3035.
LATO_TILE_M = 100_000
COMPONENTI = ("U", "E")

Tile = tuple[int, int]


def tile_per_limiti(minx: float, miny: float, maxx: float, maxy: float) -> list[Tile]:
    """Le tile (E, N) che coprono un rettangolo EPSG:3035."""
    e0, e1 = math.floor(minx / LATO_TILE_M), math.floor(maxx / LATO_TILE_M)
    n0, n1 = math.floor(miny / LATO_TILE_M), math.floor(maxy / LATO_TILE_M)
    return [(e, n) for e in range(e0, e1 + 1) for n in range(n0, n1 + 1)]


def nome(tile: Tile, componente: str, release: str) -> str:
    e, n = tile
    return f"EGMS_L3_E{e}N{n}_100km_{componente}_{release}_1"


async def scarica_tile(
    cartella: Path, tile: Tile, componente: str, *, release: str, url: str, token: str
) -> Path | None:
    """Il GeoTIFF della tile, scaricato se manca. ``None`` se la tile non esiste.

    Gli errori di rete e un token scaduto (401/403) alzano: un sync annuale
    a metà va rifatto, non scritto per metà dell'Italia.
    """
    base = nome(tile, componente, release)
    tiff = cartella / f"{base}.tiff"
    assente = cartella / f"{base}.assente"
    if tiff.exists():
        return tiff
    if assente.exists():
        return None
    cartella.mkdir(parents=True, exist_ok=True)
    resp = await fetch_with_retry(
        "GET",
        f"{url.rstrip('/')}/{base}.zip",
        client=await SharedHttpClient.get(),
        params={"id": token},
    )
    if resp.status_code == 404:
        assente.touch()
        return None
    if resp.status_code != 200:
        raise RuntimeError(f"EGMS {base}: HTTP {resp.status_code} (token scaduto?)")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        dati = z.read(f"{base}.tiff")
    parziale = tiff.with_suffix(".part")
    parziale.write_bytes(dati)
    parziale.rename(tiff)
    log.info("egms.tile.scaricata", tile=base, mb=round(len(resp.content) / 1e6, 1))
    return tiff


__all__ = ["COMPONENTI", "LATO_TILE_M", "Tile", "nome", "scarica_tile", "tile_per_limiti"]
