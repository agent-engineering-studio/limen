"""Il Bollettino di criticità nazionale/allerta della Protezione Civile.

Pubblicato ogni giorno entro le 16:00 nel repository GitHub del Dipartimento
(`pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica`, CC-BY 4.0), come
GeoJSON per oggi e per domani. È già strutturato: nessun modello linguistico
lo legge, lo si importa.

Nomi dei file, livelli e zone vengono dal pacchetto ``dpc-radar``
(``dpc_radar.bulletins``); le richieste passano da ``_http`` con il suo ``send``.

La lettura degrada a un risultato neutro (``None``) se GitHub non risponde:
il confronto con l'allerta ufficiale è un'informazione in più, non una
condizione per far girare il resto.
"""

from __future__ import annotations

from typing import Any

import httpx
from dpc_radar import DpcRadarError
from dpc_radar.bulletins import API, Bulletin, fetch, issued, latest_name
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

_DEGRADO: tuple[type[Exception], ...] = (
    httpx.HTTPError,
    RetryError,
    OSError,
    KeyError,
    ValueError,
    DpcRadarError,
)
_SENZA_ELENCO: tuple[type[Exception], ...] = (*_DEGRADO, StopIteration)


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    return await fetch_with_retry(method, url, client=await SharedHttpClient.get(), **kwargs)


async def ultimo_nome() -> str | None:
    """Il nome dell'ultimo bollettino pubblicato, o ``None``."""
    try:
        return await latest_name(send=_send)
    except _DEGRADO as exc:
        log.warning("integration.degraded", source="dpc_bollettini", error=str(exc))
        return None


async def nomi() -> list[str]:
    """Tutti i bollettini dell'archivio (``…_today.json``), dal più vecchio; ``[]`` se non si legge.

    Tre chiamate all'albero del repository, come :func:`ultimo_nome`: serve al
    confronto con la pioggia caduta (#629), che vuole il bollettino di ogni giorno.
    """
    try:
        cartella = f"{API}/git/trees/master"
        for ramo in ("files", "geojson"):
            albero = (await _send("GET", cartella)).json()["tree"]
            cartella = f"{API}/git/trees/" + next(t["sha"] for t in albero if t["path"] == ramo)
        elenco = (await _send("GET", cartella)).json()["tree"]
    except _SENZA_ELENCO as exc:
        log.warning("integration.degraded", source="dpc_bollettini", error=str(exc))
        return []
    return sorted(t["path"] for t in elenco if issued(t["path"]) is not None)


async def scarica(nome: str) -> Bulletin | None:
    """Oggi e domani del bollettino ``nome``, o ``None`` se non si legge."""
    try:
        return await fetch(nome, send=_send)
    except _DEGRADO as exc:
        log.warning("integration.degraded", source="dpc_bollettini", file=nome, error=str(exc))
        return None
