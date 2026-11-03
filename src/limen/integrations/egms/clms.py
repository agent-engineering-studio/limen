"""L'archivio EGMS con la chiave di servizio del Copernicus Land Monitoring Service.

Firma della chiave, corpo delle ricerche, lettura delle risposte ed
estrazione del GeoTIFF vengono dal pacchetto ``egms-client`` (estratto da
Limen, Apache-2.0); il traffico resta qui e passa da ``fetch_with_retry`` come
ogni chiamata esterna: il ``EgmsArchive`` del pacchetto ha un retry suo.
Qui resta anche come Limen trova la chiave (``EGMS__SERVICE_KEY`` o
``EGMS__SERVICE_KEY_FILE``).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from egms_client import (
    Component,
    EgmsError,
    Search,
    ServiceKey,
    Tile,
    Token,
    check_download,
    download_url,
    extract_tiff,
    latest_hit,
    parse_releases,
    parse_search,
    parse_token,
    search_body,
    tile_prefix,
    token_request,
)

from limen.config.settings import EgmsSettings
from limen.core.logging import get_logger
from limen.integrations._http import fetch_with_retry

log = get_logger(__name__)

#: Il token dura un'ora: si rinnova prima, perché un sync d'Italia dura di più.
_MARGINE_S = 300


def _sotto_release(nome: str) -> int:
    coda = nome.rsplit("_", 1)[-1]
    return int(coda) if coda.isdigit() else 0


class Archivio:
    """Release, ricerche e tile dell'archivio EGMS, con il token rinnovato."""

    def __init__(self, chiave: ServiceKey, *, archive_url: str) -> None:
        self._chiave = chiave
        self._archivio = archive_url.rstrip("/")
        self._token: Token | None = None
        # Le tile si scaricano in parallelo: un token solo per tutte.
        self._blocco = asyncio.Lock()

    async def _intestazioni(self) -> dict[str, str]:
        async with self._blocco:
            adesso = time.time()
            if self._token is None or adesso > self._token.expires_at - _MARGINE_S:
                resp = await fetch_with_retry(
                    "POST",
                    self._chiave.token_uri,
                    data=token_request(self._chiave, now=int(adesso)),
                    headers={"Accept": "application/json"},
                )
                self._token = parse_token(resp.status_code, resp.content, now=adesso)
            return self._token.headers()

    async def releases(self) -> list[str]:
        """Le release pubblicate, dalla più vecchia (``["2020-2024", "2020-2025"]``)."""
        resp = await fetch_with_retry(
            "GET", f"{self._archivio}/releases", headers=await self._intestazioni()
        )
        resp.raise_for_status()
        return parse_releases(resp.content)

    async def _cerca(self, tile: Tile, componente: Component, release: str) -> Search | None:
        resp = await fetch_with_retry(
            "POST",
            f"{self._archivio}/search",
            headers=await self._intestazioni(),
            json=search_body(tile, componente, release),
        )
        resp.raise_for_status()
        return parse_search(resp.content)

    async def fetch_tile(
        self, tile: Tile, componente: Component, release: str, cartella: Path
    ) -> Path | None:
        """Il GeoTIFF della velocità media in ``cartella``, scaricato se manca.

        ``None`` se la tile non esiste (mare). Tutti e due gli esiti restano
        in ``cartella`` (il GeoTIFF o un segnaposto ``…absent``, gli stessi
        nomi di ``egms-client``), quindi il secondo sync non chiede niente.
        """
        prefisso = tile_prefix(tile, componente, release)
        in_cache = sorted(cartella.glob(f"{prefisso}*.tiff"), key=lambda p: _sotto_release(p.stem))
        if in_cache:
            return in_cache[-1]
        segnaposto = cartella / f"{prefisso}absent"
        if segnaposto.exists():
            return None
        cartella.mkdir(parents=True, exist_ok=True)
        ricerca = await self._cerca(tile, componente, release)
        trovata = latest_hit(ricerca) if ricerca is not None else None
        if ricerca is None or trovata is None:
            segnaposto.touch()
            return None
        # Il nome diventa un path: uno che la glob qui sopra non ritrova
        # vorrebbe dire ~60 MB scaricati a ogni sync, uno con un separatore
        # scriverebbe altrove.
        if not trovata.stem.startswith(prefisso) or "/" in trovata.filename:
            raise EgmsError(f"nome inatteso per {prefisso}: {trovata.filename!r}")
        resp = await fetch_with_retry(
            "GET", download_url(self._archivio, trovata), params={"id": ricerca.id}
        )
        if resp.status_code == 404:
            segnaposto.touch()
            return None
        tiff = extract_tiff(check_download(resp.status_code, resp.content), trovata)
        path = cartella / f"{trovata.stem}.tiff"
        parziale = path.with_name(f"{path.name}.part")
        parziale.write_bytes(tiff)
        parziale.rename(path)
        return path


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


async def archivio(s: EgmsSettings) -> Archivio | None:
    """L'archivio, o ``None`` senza chiave."""
    trovata = chiave(s)
    if trovata is None:
        return None
    return Archivio(trovata, archive_url=s.archive_url)


def perche_no(s: EgmsSettings) -> str:
    """Il motivo, per il log, per cui non c'è un archivio."""
    if s.token is not None and s.token.get_secret_value().strip():
        return "EGMS__TOKEN non è più supportato (scadeva): serve EGMS__SERVICE_KEY"
    if s.attivo:
        return "chiave EGMS impostata ma illeggibile"
    return "né EGMS__SERVICE_KEY né EGMS__SERVICE_KEY_FILE"


__all__ = ["Archivio", "archivio", "chiave", "leggi_chiave", "perche_no"]
