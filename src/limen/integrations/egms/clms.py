"""L'archivio EGMS con la chiave di servizio del Copernicus Land Monitoring Service.

Token, ricerche, download, cache e segnaposto del mare sono di
``egms_client.EgmsArchive`` (estratto da Limen, Apache-2.0). Limen gli dà il
client condiviso e ``retries=0``: ogni chiamata gira dentro
``call_with_retry``, la policy di ogni chiamata esterna. Qui restano come
Limen trova la chiave (``EGMS_SERVICE_KEY`` o ``EGMS_SERVICE_KEY_FILE``) e
gli attributi che ricava dal CSV di ogni tile.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import numpy as np
from egms_client import Component, EgmsArchive, EgmsError, ServiceKey, Tile, tile_prefix

from limen.config.settings import EgmsSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.egms.aggregate import COLONNE_ATTRIBUTI, leggi_attributi

log = get_logger(__name__)


def attributi_di(tiff: Path) -> Path:
    """Dove sta, accanto al GeoTIFF, ciò che serve del CSV della stessa tile."""
    return tiff.with_name(f"{tiff.stem}.attributi.npz")


def _salva_attributi(csv: Path, path: Path) -> None:
    """Accelerazione e stagionalità per pixel, dal CSV della tile (#380).

    ~170.000 righe per quattro colonne: qualche MB, contro i ~250 MB del CSV
    con la serie storica, che non serve e si cancella. Un CSV senza le colonne
    lascia un file vuoto, così il sync seguente non riscarica la tile per
    niente: la cella avrà accelerazione e stagionalità NULL, non zero.
    """
    try:
        colonne = leggi_attributi(csv)
    except ValueError as exc:
        log.warning("egms.attributi_assenti", tile=csv.stem, error=str(exc))
        colonne = {c: np.empty(0) for c in ("easting", "northing", *COLONNE_ATTRIBUTI)}
    parziale = path.with_name(f"{path.name}.part")
    with parziale.open("wb") as f:
        np.savez(f, **colonne)
    parziale.rename(path)
    csv.unlink()


def _sotto_release(nome: str) -> int:
    coda = nome.rsplit("_", 1)[-1]
    return int(coda) if coda.isdigit() else 0


def _occupato(exc: BaseException) -> bool:
    """Un download o un token rifiutati perché l'archivio è occupato (429, 5xx)."""
    stato = exc.status_code if isinstance(exc, EgmsError) else None
    return stato is not None and (stato >= 500 or stato == 429)


async def releases(a: EgmsArchive) -> list[str]:
    """Le release pubblicate, dalla più vecchia (``["2020-2024", "2020-2025"]``)."""
    return await call_with_retry(a.releases, anche=_occupato)


async def scarica_tile(
    a: EgmsArchive,
    tile: Tile,
    componente: Component,
    release: str,
    cartella: Path,
    *,
    attributi: bool = False,
) -> Path | None:
    """Il GeoTIFF della velocità media in ``cartella``, scaricato se manca.

    ``None`` se la tile non esiste (mare). Tutti e due gli esiti restano in
    ``cartella`` (il GeoTIFF o il segnaposto ``…absent`` della libreria),
    quindi il secondo sync non chiede niente. Con ``attributi`` salva anche
    :func:`attributi_di` dal CSV dello stesso ZIP; una tile scaricata prima,
    che ha il GeoTIFF e non gli attributi, si riscarica una volta.
    """
    if attributi:
        # Gli attributi sono un file di Limen: per la libreria, che cerca il
        # CSV, la tile mancherebbe a ogni sync.
        prefisso = tile_prefix(tile, componente, release)
        in_cache = sorted(cartella.glob(f"{prefisso}*.tiff"), key=lambda p: _sotto_release(p.stem))
        if in_cache and attributi_di(in_cache[-1]).exists():
            return in_cache[-1]
    tiff = await call_with_retry(
        lambda: a.fetch_tile(
            tile, componente, release, cartella, keep=("tiff", "csv") if attributi else ("tiff",)
        ),
        anche=_occupato,
    )
    if tiff is not None and attributi:
        await asyncio.to_thread(_salva_attributi, tiff.with_suffix(".csv"), attributi_di(tiff))
    return tiff


def leggi_chiave(testo: str) -> ServiceKey | None:
    """La chiave di servizio dal JSON, ``None`` se vuota o incompleta."""
    if not testo.strip():
        return None
    try:
        return ServiceKey.from_json(testo)
    except ValueError as exc:
        # Impostata ma illeggibile (PEM troncato, virgolette perse nel .env):
        # senza questo log il sync direbbe solo «nessuna chiave».
        log.warning("egms.chiave_non_valida", error=str(exc)[:200])
        return None


def chiave(s: EgmsSettings) -> ServiceKey | None:
    """La chiave dalla variabile o dal file; ``None`` se nessuno dei due la dà."""
    if s.service_key is not None and s.service_key.get_secret_value().strip():
        return leggi_chiave(s.service_key.get_secret_value())
    if s.service_key_file and s.service_key_file.strip():
        try:
            return leggi_chiave(Path(s.service_key_file).expanduser().read_text())
        except OSError as exc:
            log.warning("egms.file_chiave_illeggibile", path=s.service_key_file, error=str(exc))
    return None


async def archivio(s: EgmsSettings) -> EgmsArchive | None:
    """L'archivio, o ``None`` senza chiave."""
    trovata = chiave(s)
    if trovata is None:
        return None
    return EgmsArchive(await SharedHttpClient.get(), trovata, archive_url=s.archive_url, retries=0)


def perche_no(s: EgmsSettings) -> str:
    """Il motivo, per il log, per cui non c'è un archivio."""
    if s.token is not None and s.token.get_secret_value().strip():
        return "EGMS__TOKEN non è più supportato (scadeva): serve EGMS_SERVICE_KEY"
    if s.attivo:
        return "chiave EGMS impostata ma illeggibile"
    return "né EGMS_SERVICE_KEY né EGMS_SERVICE_KEY_FILE"


__all__ = [
    "archivio",
    "attributi_di",
    "chiave",
    "leggi_chiave",
    "perche_no",
    "releases",
    "scarica_tile",
]
