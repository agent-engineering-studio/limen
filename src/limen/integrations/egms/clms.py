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

Firma, ricerca e lettura delle risposte vengono dal pacchetto ``egms-client``
(estratto da Limen, Apache-2.0); qui resta il traffico, che passa da
``fetch_with_retry`` come ogni chiamata esterna.
"""

from __future__ import annotations

import time

from egms_client import (
    ARCHIVE_URL,
    Component,
    Search,
    ServiceKey,
    Token,
    assertion,
    parse_releases,
    parse_search,
    parse_token,
    search_body,
    token_request,
)

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

ARCHIVIO = ARCHIVE_URL
#: Il token dura un'ora: si rinnova prima, perché un sync d'Italia dura di più.
_MARGINE_S = 300


def asserzione(chiave: ServiceKey, *, adesso: int) -> str:
    """Il JWT RS256 che la chiave di servizio firma per chiedere un token."""
    return assertion(chiave, now=adesso)


class Sessione:
    """Un token di accesso, rinnovato quando sta per scadere."""

    def __init__(self, chiave: ServiceKey, *, archivio: str = ARCHIVIO) -> None:
        self._chiave = chiave
        self._archivio = archivio.rstrip("/")
        self._token: Token | None = None

    async def _intestazioni(self) -> dict[str, str]:
        adesso = time.time()
        if self._token is None or adesso > self._token.expires_at - _MARGINE_S:
            resp = await fetch_with_retry(
                "POST",
                self._chiave.token_uri,
                client=await SharedHttpClient.get(),
                data=token_request(self._chiave, now=int(adesso)),
                headers={"Accept": "application/json"},
            )
            self._token = parse_token(resp.status_code, resp.content, now=adesso)
        return self._token.headers()

    async def release(self) -> list[str]:
        resp = await fetch_with_retry(
            "GET",
            f"{self._archivio}/releases",
            client=await SharedHttpClient.get(),
            headers=await self._intestazioni(),
        )
        return parse_releases(resp.content)

    async def cerca(
        self, tile: tuple[int, int], componente: Component, release: str
    ) -> Search | None:
        """La ricerca con cui scaricare la tile, o ``None`` se la tile non esiste (mare)."""
        resp = await fetch_with_retry(
            "POST",
            f"{self._archivio}/search",
            client=await SharedHttpClient.get(),
            headers=await self._intestazioni(),
            json=search_body(tile, componente, release),
        )
        return parse_search(resp.content)


def leggi_chiave(testo: str) -> ServiceKey | None:
    """La chiave di servizio dal JSON, ``None`` se vuota o incompleta."""
    if not testo.strip():
        return None
    try:
        return ServiceKey.from_json(testo)
    except ValueError as exc:
        # Impostata ma illeggibile (PEM troncato, virgolette perse nel .env):
        # senza questo log il sync direbbe «né chiave né token».
        log.warning("egms.chiave_non_valida", error=str(exc)[:200])
        return None


__all__ = ["ARCHIVIO", "Sessione", "asserzione", "leggi_chiave"]
