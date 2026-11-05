"""DPC national radar — SRI (Surface Rainfall Intensity) client.

Open data of the Dipartimento della Protezione Civile radar platform
(https://radar-api.protezionecivile.it, CC-BY-SA 4.0). The SRI product is
a national 1 km GeoTIFF in mm/h refreshed every 5 minutes — the trigger
signal for the nowcast job: radar decides *when* to run, the existing
scoring pipeline decides *what* to alert.

The CUM products (``CUM3``/``6``/``12``/``24``) are the rain already fallen:
the «Merging» of radar and rain gauges, 0.01° in EPSG:4326, refreshed every
30 minutes. The flood engine reads them as the observed part of its pluvial
window (#199), after checking each frame against the one before it (#235).

Requests, product parsing and the decoded frame (:class:`RainGrid`, ``NaN``
where there is no data) come from the ``dpc-radar`` package; the HTTP goes
through ``_http`` via its ``send`` hook, so the package's own retry is never
used.

Read-only integration: every failure degrades to ``None`` and logs
``integration.degraded`` — it never raises.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
from dpc_radar import Absent, DpcRadarError, RadarClient, RainGrid
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

#: Un fotogramma CUM nuovo ogni 30 minuti (`period: PT30M` dell'API).
CUM_PERIOD = timedelta(minutes=30)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
    KeyError,
    ValueError,
    DpcRadarError,
)


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Every request through the shared client and its retry policy.

    The package passes its own ``timeout`` for the GeoTIFF: dropped, so the
    shared client's timeouts keep applying as they did before the package.
    """
    kwargs.pop("timeout", None)
    return await fetch_with_retry(method, url, client=await SharedHttpClient.get(), **kwargs)


async def _send_archivio(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Come :func:`_send`, ma la richiesta del link non passa dalla politica di retry.

    Un fotogramma scaduto risponde 500 con il 403 di S3 nel corpo: ritentato
    sarebbero quattro tentativi con backoff per niente, e poi un ``RetryError``
    al posto di :data:`~dpc_radar.ABSENT`. Un ``RetryError`` esce come
    ``httpx.HTTPError``: è ciò che ``dpc_radar.archive`` conta come fotogramma
    fallito, da ritentare al giro dopo; qualunque altro tipo fermerebbe l'archivio.
    """
    try:
        if method == "POST":
            kwargs.pop("timeout", None)
            client = await SharedHttpClient.get()
            return await client.request(method, url, **kwargs)
        return await _send(method, url, **kwargs)
    except RetryError as exc:
        raise httpx.TransportError(str(exc)) from exc


def radar_archivio() -> RadarClient:
    """Il client per l'archivio «Merging»: vedi :func:`_send_archivio`."""
    return RadarClient(send=_send_archivio)


def _degraded(label: str, exc: BaseException | str) -> None:
    if isinstance(exc, str):
        log.warning("integration.degraded", label=label, error=exc)
        return
    log.warning("integration.degraded", label=label, error=str(exc), error_type=type(exc).__name__)


async def _download(
    product_type: str, cached: RainGrid | None = None, *, at: datetime | None = None
) -> RainGrid | None:
    """The most recent frame of ``product_type`` (or the one issued ``at``);
    ``cached`` if it is still that one."""
    label = f"dpc.{product_type.lower()}"
    radar = RadarClient(send=_send)
    try:
        grid = (
            await radar.latest(product_type, cached=cached)
            if at is None
            else await radar.at(product_type, at)
        )
    except _DEGRADATION_EXC as exc:
        _degraded(label, exc)
        return None
    if isinstance(grid, Absent):
        _degraded(label, "frame no longer kept")
        return None
    if grid is not cached:
        log.info(
            "dpc.radar.fetched",
            product=product_type,
            observed_at=grid.time.isoformat(),
            shape=grid.data.shape,
        )
    return grid


async def get_latest_sri() -> RainGrid | None:
    """Fetch + parse the most recent national SRI frame (None on failure)."""
    return await _download("SRI")


#: L'ultimo fotogramma CUM per durata. Una regione dopo l'altra chiede lo
#: stesso file nazionale (~2 MB, nuovo ogni 30 minuti): si riscarica solo
#: quando il DPC ne pubblica uno nuovo.
_cum_cache: dict[int, RainGrid] = {}
#: Il fotogramma prima dell'ultimo: è quello contro cui si controlla il nuovo
#: (#235), quindi a regime il controllo non scarica niente in più.
_cum_previous: dict[int, RainGrid] = {}


async def get_latest_cum(hours: int) -> RainGrid | None:
    """The most recent national rain accumulation over ``hours`` (None on failure)."""
    old = _cum_cache.get(hours)
    grid = await _download(f"CUM{hours}", old)
    if grid is not None:
        if old is not None and old.time != grid.time:
            _cum_previous[hours] = old
        _cum_cache[hours] = grid
    return grid


async def get_cum_at(hours: int, observed_at: datetime) -> RainGrid | None:
    """The accumulation over ``hours`` issued at ``observed_at`` (None on failure)."""
    for g in (_cum_cache.get(hours), _cum_previous.get(hours)):
        if g is not None and g.time == observed_at:
            return g
    grid = await _download(f"CUM{hours}", at=observed_at)
    if grid is not None:
        _cum_previous[hours] = grid
    return grid


__all__ = [
    "CUM_PERIOD",
    "RainGrid",
    "get_cum_at",
    "get_latest_cum",
    "get_latest_sri",
    "radar_archivio",
]
