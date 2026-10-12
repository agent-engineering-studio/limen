"""L'archivio EGMS con la chiave di servizio del Copernicus Land Monitoring Service.

Il parametro ``id`` dei link di download non è un'autorizzazione: è l'id di
una **ricerca** (`/archive/search`), e scade se non lo si usa. Il token che si
copiava dall'Explorer era uno di questi. Con la chiave di servizio CLMS
(profilo su land.copernicus.eu → «API Tokens», un JSON con ``client_id``,
``user_id``, ``private_key``, ``token_uri``) si firma un JWT, lo si scambia per
un token di accesso valido un'ora, e con quello si fa una ricerca nuova per
ogni tile: niente da copiare a mano, a nessuna release.

Lo stesso token apre `/archive/releases`, che è l'unico modo di sapere che è
uscita una release nuova: senza login l'archivio risponde «Please log in» a
tutto (verificato l'11 ottobre 2026).
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

ARCHIVIO = "https://egms.land.copernicus.eu/insar-api/archive"
_TIPO = {"U": "ORTHO-UP", "E": "ORTHO-EAST"}
#: Il token dura un'ora: si rinnova prima, perché un sync d'Italia dura di più.
_DURATA_S = 3600
_MARGINE_S = 300


def _b64(dati: bytes) -> bytes:
    return base64.urlsafe_b64encode(dati).rstrip(b"=")


def asserzione(chiave: dict[str, Any], *, adesso: int) -> str:
    """Il JWT RS256 che la chiave di servizio firma per chiedere un token."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    testa = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    corpo = _b64(
        json.dumps(
            {
                "iss": chiave["client_id"],
                "sub": chiave["user_id"],
                "aud": chiave["token_uri"],
                "iat": adesso,
                "exp": adesso + _DURATA_S,
            }
        ).encode()
    )
    privata = serialization.load_pem_private_key(chiave["private_key"].encode(), password=None)
    if not isinstance(privata, rsa.RSAPrivateKey):
        raise ValueError("la chiave di servizio CLMS non è RSA")
    firma = _b64(privata.sign(testa + b"." + corpo, padding.PKCS1v15(), hashes.SHA256()))
    return (testa + b"." + corpo + b"." + firma).decode()


def release_archivio(release: str) -> str:
    """``2020_2024`` (nomi dei file) → ``2020-2024`` (API dell'archivio)."""
    return release.replace("_", "-")


class Sessione:
    """Un token di accesso, rinnovato quando sta per scadere."""

    def __init__(self, chiave: dict[str, Any], *, archivio: str = ARCHIVIO) -> None:
        self._chiave = chiave
        self._archivio = archivio.rstrip("/")
        self._token: str | None = None
        self._scade = 0.0

    async def _intestazioni(self) -> dict[str, str]:
        adesso = time.time()
        if self._token is None or adesso > self._scade - _MARGINE_S:
            resp = await fetch_with_retry(
                "POST",
                self._chiave["token_uri"],
                client=await SharedHttpClient.get(),
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": asserzione(self._chiave, adesso=int(adesso)),
                },
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"CLMS: token negato (HTTP {resp.status_code})")
            dati = resp.json()
            self._token = str(dati["access_token"])
            self._scade = adesso + float(dati.get("expires_in", _DURATA_S))
        return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}

    async def release(self) -> list[str]:
        resp = await fetch_with_retry(
            "GET",
            f"{self._archivio}/releases",
            client=await SharedHttpClient.get(),
            headers=await self._intestazioni(),
        )
        dati = resp.json()
        if not isinstance(dati, list):
            raise RuntimeError(f"EGMS: risposta inattesa da /releases: {str(dati)[:200]}")
        return [str(r) for r in dati]

    async def cerca(self, tile: tuple[int, int], componente: str, release: str) -> str | None:
        """L'id di ricerca con cui scaricare la tile, o ``None`` se non esiste."""
        e, n = tile
        resp = await fetch_with_retry(
            "POST",
            f"{self._archivio}/search",
            client=await SharedHttpClient.get(),
            headers=await self._intestazioni(),
            json={
                "tileId": f"E{e}N{n}",
                "releases": [release_archivio(release)],
                "levels": ["L3"],
                "productType": _TIPO[componente],
            },
        )
        dati = resp.json()
        messaggio = str(dati.get("message") or "")
        # Una tile in mare o fuori copertura non ha un catalogo: l'archivio
        # risponde così, non con una ricerca vuota (verificato su E40N15).
        if not dati.get("status") and messaggio.startswith("Invalid tile ID"):
            return None
        if not dati.get("status"):
            raise RuntimeError(f"EGMS: ricerca rifiutata: {str(dati.get('message'))[:200]}")
        return str(dati["id"]) if dati.get("hits") else None


def leggi_chiave(testo: str) -> dict[str, Any] | None:
    """La chiave di servizio dal JSON, ``None`` se vuota o incompleta."""
    if not testo.strip():
        return None
    chiave = json.loads(testo)
    campi = ("client_id", "user_id", "private_key", "token_uri")
    if not isinstance(chiave, dict) or any(not chiave.get(c) for c in campi):
        return None
    return chiave


__all__ = ["ARCHIVIO", "Sessione", "asserzione", "leggi_chiave", "release_archivio"]
