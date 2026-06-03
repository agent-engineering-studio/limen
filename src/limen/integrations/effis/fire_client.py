"""EFFIS burnt-area perimeters client.

EFFIS exposes burnt-area features through its rapid-damage-assessment
WMS/WFS endpoints. The programmatic access this client targets is the
WFS GetFeature on
``https://maps.effis.emergency.copernicus.eu/gwis``; full annual
perimeter shapefiles and dNBR rasters often require a manual EFFIS data
request, which we mark as TODO and surface in the operator log.

Returns:
    Raw GeoJSON features (one feature = one burnt-area polygon). The
    sync job converts them to :class:`FirePerimeter`.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Iterable

log = get_logger(__name__)

# Default WFS endpoint and typeName. Override at construction time if
# Copernicus moves endpoints.
DEFAULT_WFS_URL = "https://maps.effis.emergency.copernicus.eu/gwis/ows"
DEFAULT_TYPENAME = "effis:ba.fires"

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


class EffisHttpClient:
    """Concrete :class:`EffisClient` Protocol implementation."""

    def __init__(
        self,
        *,
        wfs_url: str = DEFAULT_WFS_URL,
        typename: str = DEFAULT_TYPENAME,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._wfs_url = wfs_url
        self._typename = typename
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def fetch_perimeters(
        self,
        *,
        bbox: tuple[float, float, float, float],
        start: date,
        end: date,
    ) -> Iterable[dict[str, Any]]:
        """Return burnt-area features intersecting ``bbox`` for ``[start, end]``.

        On terminal failure, returns ``[]`` and logs ``integration.degraded``.
        """
        params: dict[str, Any] = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": self._typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326",
            "CQL_FILTER": (
                f"firedate >= '{start.isoformat()}' AND firedate <= '{end.isoformat()}'"
            ),
        }
        log.info(
            "effis.perimeters.fetch",
            bbox=bbox,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        try:
            resp = await fetch_with_retry(
                "GET", self._wfs_url, client=await self._client(), params=params
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="effis.perimeters",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        if resp.status_code == 204 or not resp.content:
            return []

        try:
            payload = resp.json()
        except ValueError:
            log.warning("effis.perimeters.bad_payload", status=resp.status_code)
            return []
        features = list(payload.get("features") or [])
        log.info("effis.perimeters.fetched", count=len(features))
        return features

    async def fetch_dnbr(self, *, perimeter_id: str) -> bytes | None:
        """Best-effort dNBR raster download for a single perimeter.

        EFFIS dNBR products typically require the manual data-request
        workflow (https://forest-fire.emergency.copernicus.eu/applications/data-and-services).
        This client returns ``None`` and logs a TODO so the workflow
        proceeds without dNBR; a future prompt can plug a programmatic
        endpoint here when Copernicus publishes one.
        """
        log.info(
            "effis.dnbr.not_implemented",
            perimeter_id=perimeter_id,
            note=(
                "EFFIS dNBR rasters require the manual data-request workflow; "
                "implement once Copernicus exposes a programmatic endpoint."
            ),
        )
        return None
