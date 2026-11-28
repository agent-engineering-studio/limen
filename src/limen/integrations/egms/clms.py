"""L'archivio EGMS con la chiave di servizio del Copernicus Land Monitoring Service.

Token, ricerche, download, cache e segnaposto del mare sono di
``egms_client.EgmsArchive`` (estratto da Limen, Apache-2.0). Limen gli dà il
client condiviso e ``retries=0``: ogni chiamata gira dentro
``call_with_retry``, la policy di ogni chiamata esterna. Anche gli attributi
di una tile (accelerazione, stagionalità) sono della libreria:
``fetch_tile(keep=("tiff", "attributes"))``. Qui resta come Limen trova la
chiave (``EGMS_SERVICE_KEY`` o ``EGMS_SERVICE_KEY_FILE``).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

import numpy as np
from egms_client import Component, EgmsArchive, EgmsError, ServiceKey, Tile

from limen.config.settings import EgmsSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.egms.aggregate import COLONNE_ATTRIBUTI

log = get_logger(__name__)


def attributi_di(tiff: Path) -> Path:
    """Dove ``egms-client`` tiene, accanto al GeoTIFF, gli attributi della stessa tile."""
    return tiff.with_suffix(".attributes.csv")


def migra_attributi(cartella: Path) -> int:
    """Gli attributi salvati da Limen (``.attributi.npz``) riscritti come li cerca la libreria.

    Senza, al primo sync ogni tile verticale si riscaricherebbe (~250 MB
    l'una) per avere il suo ``.attributes.csv``. Gli stessi numeri, colonna
    per colonna: il CSV si legge in float64 come l'``.npz``. Un ``.npz``
    vuoto (un CSV senza quelle colonne) dà un file con la sola intestazione.
    Restituisce quanti ne ha migrati.
    """
    migrati = 0
    for vecchio in sorted(cartella.glob("*.attributi.npz")):
        nuovo = cartella / f"{vecchio.name.removesuffix('.attributi.npz')}.attributes.csv"
        if not nuovo.exists():
            colonne = ["easting", "northing", *COLONNE_ATTRIBUTI]
            with np.load(vecchio) as a:
                valori = [a[c] for c in colonne]
            parziale = nuovo.with_name(f"{nuovo.name}.part")
            with parziale.open("w", newline="") as f:
                scrivi = csv.writer(f, lineterminator="\n")
                scrivi.writerow(colonne)
                scrivi.writerows(zip(*(v.tolist() for v in valori), strict=True))
            parziale.rename(nuovo)
        vecchio.unlink()
        migrati += 1
    if migrati:
        log.info("egms.attributi_migrati", n=migrati)
    return migrati


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
    quindi il secondo sync non chiede niente. Con ``attributi`` la libreria
    tiene anche :func:`attributi_di`, dal CSV dello stesso ZIP; una tile
    scaricata prima, che ha il GeoTIFF e non gli attributi, si riscarica una
    volta.
    """
    keep: tuple[Literal["tiff", "attributes"], ...] = (
        ("tiff", "attributes") if attributi else ("tiff",)
    )
    return await call_with_retry(
        lambda: a.fetch_tile(tile, componente, release, cartella, keep=keep),
        anche=_occupato,
    )


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
    "migra_attributi",
    "perche_no",
    "releases",
    "scarica_tile",
]
