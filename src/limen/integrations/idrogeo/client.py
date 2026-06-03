"""ISPRA IdroGEO WFS client.

GeoServer endpoint:
    ``https://idrogeo.isprambiente.it/geoserver/idrogeo/frane/ows``

Standard WFS 2.0 ``GetFeature`` calls with GeoJSON output and
``srsName=EPSG:4326``. Per-region open-data downloads
(Shapefile/GeoJSON) are intentionally **not** implemented here — the WFS
endpoint covers everything we need and is the only way to get
incremental updates. Falling back to the bulk Shapefile is a TODO if
WFS ever stops being maintained.

Default typeName mapping (override at construction time when ISPRA
changes layer names):

* IFFI points / polys / lines: ``idrogeo:iffi_*``
* PAI hazard:                  ``idrogeo:pai_pericolosita``
* Susceptibility:              ``idrogeo:suscettibilita``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Iterable

    from shapely.geometry.base import BaseGeometry

log = get_logger(__name__)

DEFAULT_OWS_URL = "https://idrogeo.isprambiente.it/geoserver/idrogeo/frane/ows"

DEFAULT_TYPENAMES = {
    "iffi_points": "idrogeo:iffi_punti",
    "iffi_polys": "idrogeo:iffi_aree",
    "iffi_lines": "idrogeo:iffi_lineari",
    "pai": "idrogeo:pai_pericolosita_frane",
    "susceptibility": "idrogeo:suscettibilita",
}

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


def _bbox_str_from_geom(geom: BaseGeometry) -> str:
    """Render a Shapely bbox as the WFS-2.0 ``minx,miny,maxx,maxy,EPSG:4326`` form."""
    min_x, min_y, max_x, max_y = geom.bounds
    return f"{min_x},{min_y},{max_x},{max_y},EPSG:4326"


class IdroGeoHttpClient:
    """Concrete :class:`IdroGeoClient` Protocol implementation."""

    def __init__(
        self,
        *,
        ows_url: str = DEFAULT_OWS_URL,
        typenames: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._ows = ows_url
        self._typenames = typenames or DEFAULT_TYPENAMES
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def _get_features(
        self,
        *,
        typename: str,
        aoi_geom: BaseGeometry,
        cql_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Perform a single WFS GetFeature request and return the feature list."""
        params: dict[str, Any] = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": typename,
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
            "bbox": _bbox_str_from_geom(aoi_geom),
        }
        if cql_filter:
            params["CQL_FILTER"] = cql_filter

        log.info("idrogeo.fetch", typename=typename, bbox=params["bbox"])
        try:
            resp = await fetch_with_retry(
                "GET", self._ows, client=await self._client(), params=params
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label=f"idrogeo.{typename}",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return []

        if resp.status_code == 204 or not resp.content:
            return []
        try:
            payload = resp.json()
        except ValueError:
            log.warning("idrogeo.bad_payload", typename=typename, status=resp.status_code)
            return []
        features = list(payload.get("features") or [])
        log.info("idrogeo.fetched", typename=typename, count=len(features))
        return features

    async def fetch_iffi(
        self,
        *,
        aoi_geom: BaseGeometry,
        cql_filter: str | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Fetch IFFI features from the three WFS layers (points, polys, lines)."""
        out: list[dict[str, Any]] = []
        for key in ("iffi_points", "iffi_polys", "iffi_lines"):
            tn = self._typenames.get(key)
            if not tn:
                continue
            feats = await self._get_features(typename=tn, aoi_geom=aoi_geom, cql_filter=cql_filter)
            for f in feats:
                f.setdefault("_iffi_layer", key)
            out.extend(feats)
        return out

    async def fetch_pai(
        self,
        *,
        aoi_geom: BaseGeometry,
    ) -> Iterable[dict[str, Any]]:
        tn = self._typenames.get("pai")
        if not tn:
            return []
        return await self._get_features(typename=tn, aoi_geom=aoi_geom)

    async def fetch_susceptibility(
        self,
        *,
        aoi_geom: BaseGeometry,
    ) -> Iterable[dict[str, Any]]:
        tn = self._typenames.get("susceptibility")
        if not tn:
            return []
        return await self._get_features(typename=tn, aoi_geom=aoi_geom)
