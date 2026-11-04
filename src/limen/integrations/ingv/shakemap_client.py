"""INGV: catalogo FDSN e ShakeMap, attraverso il pacchetto ``ingv-shakemap``.

Il pacchetto (estratto da qui, Apache-2.0, ``agent-engineering-studio/ingv-shakemap``)
sa leggere INGV: le richieste, il 204 di una finestra vuota, il 404 di un evento
senza mappa, il ``properties.eventId``, l'ordine delle righe di ``grid.xml``.
Limen gli passa ``send``: ogni richiesta va per ``fetch_with_retry`` sul client
condiviso, con la politica di retry comune, e il pacchetto non ne fa di sue.

Qui resta quello che è di Limen: un guasto in lettura degrada a un risultato
neutro e scrive ``integration.degraded``, oppure, con ``solleva=True``, solleva
:class:`IngvNonDisponibileError` (il backtest lo chiede).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
from ingv_shakemap import (
    FDSN_EVENT_URL,
    Event,
    IngvClient,
    IngvError,
    ShakeMapInfo,
    shakemap_grid_url,
)
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

log = get_logger(__name__)

__all__ = [
    "FDSN_EVENT_URL",
    "IngvHttpClient",
    "IngvNonDisponibileError",
    "shakemap_grid_url",
]

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    IngvError,
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


class IngvNonDisponibileError(RuntimeError):
    """INGV non ha risposto: con ``solleva=True`` al posto del risultato vuoto.

    Il backtest lo chiede (#287, Codex su #310): un catalogo irraggiungibile
    darebbe un report «con E» identico a quello senza, e una conclusione
    sbagliata. Lo sweep invece degrada, come ogni integrazione in lettura.
    """


class IngvHttpClient:
    """INGV per Limen: il pacchetto ``ingv-shakemap`` sul client HTTP condiviso."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client
        self._ingv = IngvClient(send=self._send)

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        client = self._http if self._http is not None else await SharedHttpClient.get()
        return await fetch_with_retry(method, url, client=client, **kwargs)

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
        min_magnitude: float = 3.5,
        solleva: bool = False,
    ) -> list[Event]:
        """I terremoti di ``bbox`` tra ``start`` ed ``end``, i più recenti prima.

        Una finestra vuota (204) è ``[]`` in ogni caso; un guasto è ``[]`` con
        ``integration.degraded``, o :class:`IngvNonDisponibileError` con
        ``solleva=True``.
        """
        log.info(
            "ingv.events.fetch",
            bbox=bbox,
            start=start.isoformat(),
            end=end.isoformat(),
            min_magnitude=min_magnitude,
        )
        nessuno: list[Event] = []
        eventi = await self._leggi(
            lambda: self._ingv.events(start, end, bbox=bbox, min_magnitude=min_magnitude),
            neutro=nessuno,
            cosa="catalogo FDSN",
            label="ingv.events",
            solleva=solleva,
        )
        log.info("ingv.events.fetched", count=len(eventi))
        return eventi

    async def fetch_shakemap_grid(self, event_id: str, *, solleva: bool = False) -> bytes | None:
        """Il ``grid.xml`` grezzo di un evento; ``None`` se INGV non ha una ShakeMap (404).

        Ogni altro guasto è ``None`` con ``integration.degraded``, o
        :class:`IngvNonDisponibileError` con ``solleva=True``.
        """
        log.info("ingv.shakemap.fetch", event_id=event_id)

        async def griglia() -> bytes | None:
            grezzo = await self._ingv.shakemap_xml(event_id)
            if grezzo is None:
                log.info("ingv.shakemap.absent", event_id=event_id)
            return grezzo

        return await self._leggi(
            griglia,
            neutro=None,
            cosa=f"ShakeMap {event_id}",
            label="ingv.shakemap",
            solleva=solleva,
            event_id=event_id,
        )

    async def fetch_info(self, event_id: str, *, solleva: bool = False) -> ShakeMapInfo | None:
        """L'``info.json`` della ShakeMap (pochi kB): versione e stato, senza la griglia."""
        return await self._leggi(
            lambda: self._ingv.info(event_id),
            neutro=None,
            cosa=f"ShakeMap {event_id} info.json",
            label="ingv.shakemap.info",
            solleva=solleva,
            event_id=event_id,
        )

    async def _leggi[T](
        self,
        chiamata: Callable[[], Awaitable[T]],
        *,
        neutro: T,
        cosa: str,
        label: str,
        solleva: bool,
        **contesto: Any,
    ) -> T:
        try:
            return await chiamata()
        except _DEGRADATION_EXC as exc:
            if solleva:
                raise IngvNonDisponibileError(f"{cosa}: {exc}") from exc
            log.warning(
                "integration.degraded",
                label=label,
                error=str(exc),
                error_type=type(exc).__name__,
                **contesto,
            )
            return neutro
