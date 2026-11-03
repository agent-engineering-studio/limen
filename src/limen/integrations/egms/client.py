"""Le tile EGMS Ortho L3 dal portale Copernicus.

Il portale non ha un'API a punti: serve archivi ZIP per tile da 100 km in
EPSG:3035, uno per componente (``U`` verticale, ``E`` est-ovest), come
``EGMS_L3_E47N19_100km_U_2020_2024_1.zip``. Il nome è l'angolo in basso a
sinistra in centinaia di km: E47N19 copre 4.700.000-4.800.000 m est e
1.900.000-2.000.000 m nord. Ogni ZIP (~60 MB) contiene un CSV con le serie
temporali (~245 MB) e un GeoTIFF con la velocità media a 100 m (~4 MB): a
Limen serve solo il secondo, e solo quello si tiene.

Il download vuole l'``id`` di una ricerca nell'archivio (`clms.Sessione`, o
quello copiato dall'Explorer). Una tile che non esiste (mare, fuori
copertura) non ha ricerca o risponde 404: si lascia un segnaposto
``.assente`` perché il giro dopo non la richieda.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from egms_client import (
    COMPONENTS,
    Component,
    EgmsError,
    Search,
    check_download,
    download_url,
    extract_tiff,
    latest_hit,
    tile_prefix,
    tiles_for_bounds,
)

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

COMPONENTI = COMPONENTS
Tile = tuple[int, int]
tile_per_limiti = tiles_for_bounds


async def scarica_tile(
    cartella: Path,
    tile: Tile,
    componente: Component,
    *,
    release: str,
    archivio: str,
    id_ricerca: Callable[[], Awaitable[Search | None]],
) -> Path | None:
    """Il GeoTIFF della tile, scaricato se manca. ``None`` se la tile non esiste.

    ``id_ricerca`` si chiama solo se il file manca: una ricerca per ogni tile
    già scaricata sarebbe traffico per niente. Gli errori di rete e un id
    scaduto (401) alzano: un sync annuale a metà va rifatto, non scritto per
    metà dell'Italia.
    """
    prefisso = tile_prefix(tile, componente, release)
    presenti = sorted(cartella.glob(f"{prefisso}*.tiff"), key=_sotto_release)
    if presenti:
        return presenti[-1]
    assente = cartella / f"{prefisso.rstrip('_')}.assente"
    # Il segnaposto di prima della sotto-release letta dalla ricerca: con il
    # solo EGMS__TOKEN ignorarlo vorrebbe dire riscaricare il mare con un id
    # scaduto, cioè un 401 che ferma il sync.
    if assente.exists() or (cartella / f"{prefisso}1.assente").exists():
        return None
    cartella.mkdir(parents=True, exist_ok=True)
    ricerca = await id_ricerca()
    hit = latest_hit(ricerca) if ricerca is not None else None
    if ricerca is None or hit is None:
        assente.touch()
        return None
    if not hit.stem.startswith(prefisso) or "/" in hit.filename:
        # Un nome che il glob qui sopra non ritroverebbe significa riscaricare
        # ~60 MB a ogni giro, in silenzio; uno con «/» scriverebbe fuori.
        raise RuntimeError(f"EGMS: nome inatteso per {prefisso}: {hit.filename!r}")
    resp = await fetch_with_retry(
        "GET",
        download_url(archivio, hit),
        client=await SharedHttpClient.get(),
        params={"id": ricerca.id},
    )
    if resp.status_code == 404:
        assente.touch()
        return None
    try:
        dati = extract_tiff(check_download(resp.status_code, resp.content), hit)
    except EgmsError as exc:
        raise RuntimeError(f"EGMS {hit.stem}: {exc}") from exc
    tiff = cartella / f"{hit.stem}.tiff"
    parziale = tiff.with_suffix(".part")
    parziale.write_bytes(dati)
    parziale.rename(tiff)
    log.info("egms.tile.scaricata", tile=hit.stem, mb=round(len(resp.content) / 1e6, 1))
    return tiff


def _sotto_release(path: Path) -> int:
    coda = path.stem.rsplit("_", 1)[-1]
    return int(coda) if coda.isdigit() else 0


__all__ = ["COMPONENTI", "Tile", "scarica_tile", "tile_per_limiti"]
