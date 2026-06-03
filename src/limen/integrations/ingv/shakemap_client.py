"""INGV FDSN event client + ShakeMap grid.xml fetcher.

FDSN event web service: ``https://webservices.ingv.it/fdsnws/event/1/query``
ShakeMap grid:          ``https://shakemap.ingv.it/shake4/data/{eventID}/current/products/grid.xml``

Both endpoints sometimes 404 or 5xx — terminal failures degrade to an
empty list / ``None`` so the workflow keeps running.

`fetch_shakemap_grid` returns raw XML bytes; parsing the PGA raster
itself (XML → 2D numpy array) lives in :mod:`shakemap_grid_parser` so
the client stays a thin transport layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Iterable

log = get_logger(__name__)

FDSN_EVENT_URL = "https://webservices.ingv.it/fdsnws/event/1/query"
SHAKEMAP_GRID_URL_TEMPLATE = (
    "https://shakemap.ingv.it/shake4/data/{event_id}/current/products/grid.xml"
)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


class IngvHttpClient:
    """Concrete :class:`IngvClient` Protocol implementation."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
        min_magnitude: float = 3.5,
    ) -> Iterable[dict[str, Any]]:
        """Return FDSN event features (GeoJSON) intersecting ``bbox`` and ``[start, end]``.

        On terminal HTTP failure: returns ``[]`` and logs ``integration.degraded``.
        """
        min_lon, min_lat, max_lon, max_lat = bbox
        params: dict[str, Any] = {
            "format": "geojson",
            "starttime": start.isoformat(),
            "endtime": end.isoformat(),
            "minlatitude": min_lat,
            "maxlatitude": max_lat,
            "minlongitude": min_lon,
            "maxlongitude": max_lon,
            "minmagnitude": min_magnitude,
            "orderby": "time",
        }
        log.info(
            "ingv.events.fetch",
            bbox=bbox,
            start=start.isoformat(),
            end=end.isoformat(),
            min_magnitude=min_magnitude,
        )
        try:
            resp = await fetch_with_retry(
                "GET", FDSN_EVENT_URL, client=await self._client(), params=params
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="ingv.events",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        # The FDSN event service sometimes returns 204/No Content for empty windows.
        if resp.status_code == 204 or not resp.content:
            return []

        payload = resp.json()
        features = list(payload.get("features") or [])
        log.info("ingv.events.fetched", count=len(features))
        return features

    async def fetch_shakemap_grid(self, event_id: str) -> bytes | None:
        """Return the raw ``grid.xml`` for ``event_id``, or ``None`` if not published.

        404 is treated as "no ShakeMap" (a legitimate state for small events);
        5xx is treated as transient and degrades to ``None``.
        """
        url = SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=event_id)
        log.info("ingv.shakemap.fetch", event_id=event_id, url=url)
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client())
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="ingv.shakemap",
                event_id=event_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

        if resp.status_code == 404:
            log.info("ingv.shakemap.absent", event_id=event_id)
            return None
        if resp.status_code >= 400:
            log.warning(
                "ingv.shakemap.bad_status",
                event_id=event_id,
                status=resp.status_code,
            )
            return None
        return bytes(resp.content)
