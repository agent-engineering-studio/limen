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
from dpc_radar.bulletins import Bulletin, fetch, latest_name
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


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    return await fetch_with_retry(method, url, client=await SharedHttpClient.get(), **kwargs)


async def ultimo_nome() -> str | None:
    """Il nome dell'ultimo bollettino pubblicato, o ``None``."""
    try:
        return await latest_name(send=_send)
    except _DEGRADO as exc:
        log.warning("integration.degraded", source="dpc_bollettini", error=str(exc))
        return None


async def scarica(nome: str) -> Bulletin | None:
    """Oggi e domani del bollettino ``nome``, o ``None`` se non si legge."""
    try:
        return await fetch(nome, send=_send)
    except _DEGRADO as exc:
        log.warning("integration.degraded", source="dpc_bollettini", file=nome, error=str(exc))
        return None
