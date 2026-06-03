"""External-source client Protocols.

These Protocols are intentionally narrow: each method matches one
domain-level operation, not one HTTP endpoint. That keeps callers (the
scoring engine, MAF agents in later phases) decoupled from API shapes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

    from shapely.geometry import Polygon
    from shapely.geometry.base import BaseGeometry


@runtime_checkable
class OpenMeteoClient(Protocol):
    """Weather and soil-moisture access (forecast + ERA5 historical)."""

    async def get_meteo_snapshot(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        window_start: datetime,
        window_end: datetime,
    ) -> Any:
        """Return an hourly :class:`MeteoSnapshot` for ``[window_start, window_end]``."""

    async def get_api(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        as_of: date,
        days: int,
    ) -> dict[str, float]:
        """Return the Antecedent Precipitation Index (sum of precip in mm)."""


@runtime_checkable
class IdroGeoClient(Protocol):
    """ISPRA IdroGEO access — IFFI landslides, PAI hazard, susceptibility."""

    async def fetch_iffi(
        self,
        *,
        aoi_geom: BaseGeometry,
        cql_filter: str | None = None,
    ) -> Iterable[dict[str, Any]]:
        """Yield raw IFFI features (GeoJSON-style dicts) within ``aoi_geom``."""

    async def fetch_pai(
        self,
        *,
        aoi_geom: BaseGeometry,
    ) -> Iterable[dict[str, Any]]:
        """Yield raw PAI hazard features within ``aoi_geom``."""

    async def fetch_susceptibility(
        self,
        *,
        aoi_geom: BaseGeometry,
    ) -> Iterable[dict[str, Any]]:
        """Yield raw susceptibility features (polygons + class) within ``aoi_geom``."""


@runtime_checkable
class IngvClient(Protocol):
    """INGV (Istituto Nazionale di Geofisica e Vulcanologia) access."""

    async def fetch_events(
        self,
        *,
        bbox: tuple[float, float, float, float],
        start: datetime,
        end: datetime,
        min_magnitude: float = 3.5,
    ) -> Iterable[dict[str, Any]]:
        """Yield event metadata (FDSN GeoJSON features)."""

    async def fetch_shakemap_grid(self, event_id: str) -> bytes | None:
        """Return raw ShakeMap ``grid.xml`` bytes, or ``None`` when absent."""


@runtime_checkable
class EffisClient(Protocol):
    """EFFIS (European Forest Fire Information System) access."""

    async def fetch_perimeters(
        self,
        *,
        bbox: tuple[float, float, float, float] | Polygon,
        start: date,
        end: date,
    ) -> Iterable[dict[str, Any]]:
        """Yield burnt-area perimeter features for ``[start, end]``."""

    async def fetch_dnbr(
        self,
        *,
        perimeter_id: str,
    ) -> bytes | None:
        """Return raw dNBR raster bytes (GeoTIFF), or ``None`` when not available."""
