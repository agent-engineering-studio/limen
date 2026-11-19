"""I fatti del radar per l'assistente: ``dpc_radar.facts`` nel server MCP di Limen (#643).

Ogni risposta è un dizionario che nomina il fotogramma da cui viene, come è
stato letto e quanto ci si può fidare del radar in quel punto: il modello
riformula, non calcola. Le richieste passano da ``_http`` con il ``send`` del
client; i fotogrammi restano in memoria (``cache_frames``), quindi una
conversazione che chiede dieci posti scarica ogni fotogramma una volta.

Sono richieste a domanda, fuori dal conto giornaliero del runbook («Richieste
al servizio radar del DPC»), che misura lo sweep: poche, finché a chiedere è un
assistente e non una pagina pubblica.

Sola lettura: ogni errore della sorgente dà ``{}`` e ``integration.degraded``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from dpc_radar import DpcRadarError, RadarClient
from dpc_radar.bulletins import Bulletin
from dpc_radar.facts import Facts
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations.dpc import bollettini
from limen.integrations.dpc.client import _send

log = get_logger(__name__)

_DEGRADO: tuple[type[Exception], ...] = (
    httpx.HTTPError,
    RetryError,
    OSError,
    ValueError,
    KeyError,
    DpcRadarError,
)
_fatti: Facts | None = None


async def _bollettino() -> Bulletin:
    nome = await bollettini.ultimo_nome()
    letto = await bollettini.scarica(nome) if nome is not None else None
    if letto is None:
        raise DpcRadarError("the newest DPC bulletin cannot be read")
    return letto


def fatti() -> Facts:
    global _fatti
    if _fatti is None:
        _fatti = Facts(RadarClient(send=_send), bulletin=_bollettino)
    return _fatti


async def chiedi(
    domanda: str, risposta: Callable[[Facts], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    """La risposta di ``Facts``, o ``{}`` se la sorgente non risponde."""
    try:
        return await risposta(fatti())
    except _DEGRADO as exc:
        log.warning(
            "integration.degraded",
            source="dpc_radar_facts",
            domanda=domanda,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {}
