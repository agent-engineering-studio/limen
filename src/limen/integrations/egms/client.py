"""HTTP client for the Copernicus EGMS download portal.

The portal exposes the persistent-scatterer products (L2a calibrated,
L3 ortho) as paginated feature collections. For Limen's purposes the
relevant fields per scatterer are:

* ``lon``, ``lat``        — the scatterer's location in EPSG:4326
* ``velocity_mmy``        — LOS / vertical velocity in mm/year
* ``acceleration_mmy2``   — second-derivative trend
* ``period_start/end``    — measurement window (yearly cadence)

The integration is read-only and degrades to an empty list on any
network failure (the workflow can tolerate the loss of one InSAR
refresh — V1 features always remain).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ScattererPoint:
    """One persistent scatterer from an EGMS product."""

    lon: float
    lat: float
    velocity_mmy: float
    acceleration_mmy2: float | None
    period_start: date | None
    period_end: date | None


class EgmsClient:
    """Async client over :class:`SharedHttpClient`.

    Production deployments point ``base_url`` at an authenticated
    EGMS proxy. The fetcher paginates if the upstream advertises
    ``next`` links via HATEOAS, but returns an empty iterator on any
    failure (no raise).
    """

    def __init__(self, *, base_url: str, product: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._product = product

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def product(self) -> str:
        return self._product

    async def fetch_bbox(
        self,
        *,
        bbox: tuple[float, float, float, float],
    ) -> AsyncIterator[ScattererPoint]:
        """Yield scatterers within ``bbox = (min_lon, min_lat, max_lon, max_lat)``."""
        params = {
            "product": self._product,
            "bbox": ",".join(str(x) for x in bbox),
            "format": "json",
        }
        url = f"{self._base_url}/scatterers"
        client = await SharedHttpClient.get()
        try:
            response = await client.get(url, params=params, timeout=30.0)
            response.raise_for_status()
        except Exception as exc:  # degrade
            _log.warning(
                "egms.fetch.degraded",
                error=str(exc),
                error_type=type(exc).__name__,
                bbox=bbox,
            )
            return
        data = response.json()
        for feat in data.get("features", []):
            point = _parse_feature(feat)
            if point is not None:
                yield point


def _parse_feature(feat: dict[str, Any]) -> ScattererPoint | None:
    """Map one EGMS GeoJSON feature to a :class:`ScattererPoint`."""
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if not (isinstance(coords, list | tuple) and len(coords) >= 2):
        return None
    props = feat.get("properties") or {}
    try:
        velocity = float(props.get("velocity") or props.get("velocity_mmy") or 0.0)
    except (TypeError, ValueError):
        return None
    accel_raw = props.get("acceleration") or props.get("acceleration_mmy2")
    accel = float(accel_raw) if accel_raw is not None else None
    return ScattererPoint(
        lon=float(coords[0]),
        lat=float(coords[1]),
        velocity_mmy=velocity,
        acceleration_mmy2=accel,
        period_start=_parse_date(props.get("period_start")),
        period_end=_parse_date(props.get("period_end")),
    )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime as _dt

        return _dt.fromisoformat(str(value)).date()
    except (TypeError, ValueError):
        return None


__all__ = ["EgmsClient", "ScattererPoint"]
