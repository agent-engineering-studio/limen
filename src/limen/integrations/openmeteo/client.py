"""Open-Meteo HTTP client (forecast + ERA5 historical).

We deliberately call the REST API directly via ``httpx`` rather than
through the ``openmeteo-requests`` SDK: the JSON shape is simple, the
SDK pulls in extra runtime dependencies, and we want full control over
retries/timeouts (see :mod:`limen.integrations._http`).

Spatial sampling: Open-Meteo grids are at ~9 km resolution. To minimise
calls, every AOI request is sampled at the **AOI bbox centroid**; the
caller (Phase 3 scoring engine) is responsible for clustering risk
cells by their nearest meteo centroid before invoking us.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.openmeteo.dtos import MeteoSnapshot, WeatherSample

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Per project doc §2.3 — the dynamic-weather variables we need.
HOURLY_VARS = [
    "precipitation",
    "soil_moisture_0_to_7cm",
    "soil_moisture_7_to_28cm",
    "snowfall",
    "snow_depth",
]

# Exceptions classified as "external source unreachable" — degraded path.
_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


def _bbox_centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return ``(lon, lat)`` of the centroid of an EPSG:4326 bbox.

    ``bbox`` is ``(min_lon, min_lat, max_lon, max_lat)``.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    return ((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0)


def _maybe_float(seq: list[Any], i: int) -> float | None:
    if i >= len(seq):
        return None
    v = seq[i]
    return float(v) if v is not None else None


def _parse_hourly(payload: dict[str, Any]) -> list[WeatherSample]:
    hourly = payload.get("hourly") or {}
    times: list[str] = list(hourly.get("time") or [])
    precip = list(hourly.get("precipitation") or [])
    sm07 = list(hourly.get("soil_moisture_0_to_7cm") or [])
    sm728 = list(hourly.get("soil_moisture_7_to_28cm") or [])
    snowfall = list(hourly.get("snowfall") or [])
    snow_depth = list(hourly.get("snow_depth") or [])

    out: list[WeatherSample] = []
    for i, ts in enumerate(times):
        precip_v = _maybe_float(precip, i) or 0.0
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            # Open-Meteo returns naive timestamps in the requested timezone
            # (we always request UTC). Attach UTC explicitly so downstream
            # comparisons with aware datetimes work.
            parsed = parsed.replace(tzinfo=UTC)
        out.append(
            WeatherSample(
                timestamp=parsed,
                precipitation_mm=precip_v,
                soil_moisture_0_7_cm=_maybe_float(sm07, i),
                soil_moisture_7_28_cm=_maybe_float(sm728, i),
                snowfall_cm=_maybe_float(snowfall, i),
                snow_depth_m=_maybe_float(snow_depth, i),
            )
        )
    return out


class OpenMeteoHttpClient:
    """Concrete :class:`OpenMeteoClient` Protocol implementation."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def get_meteo_snapshot(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        window_start: datetime,
        window_end: datetime,
        use_archive: bool = False,
    ) -> MeteoSnapshot | None:
        """Fetch hourly weather + soil-moisture for ``[window_start, window_end]``.

        ``use_archive=True`` routes the request to the ERA5 archive API instead
        of the forecast API — required for historical windows (e.g. the
        backtest replay), which the forecast endpoint rejects with HTTP 400.

        Returns ``None`` on terminal HTTP failure (graceful degradation).
        """
        lon, lat = _bbox_centroid(bbox)
        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(HOURLY_VARS),
            "start_date": window_start.date().isoformat(),
            "end_date": window_end.date().isoformat(),
            "timezone": "UTC",
        }
        url = ARCHIVE_URL if use_archive else FORECAST_URL
        source = "open-meteo:archive" if use_archive else "open-meteo:forecast"

        log.info(
            "openmeteo.snapshot.fetch",
            aoi_id=aoi_id,
            lon=lon,
            lat=lat,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            source=source,
        )
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client(), params=params)
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="openmeteo.snapshot",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

        payload = resp.json()
        samples = _parse_hourly(payload)
        samples = [s for s in samples if window_start <= s.timestamp <= window_end]

        return MeteoSnapshot(
            centroid_lon=lon,
            centroid_lat=lat,
            window_start=window_start,
            window_end=window_end,
            samples=samples,
            source=source,
            api_version=str(payload.get("generationtime_ms", "")) or None,
        )

    async def get_api(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        as_of: date,
        days: int,
    ) -> dict[str, float]:
        """Return total precipitation in mm over the trailing ``days`` ending at ``as_of``.

        ERA5 reanalysis via the archive API. Returns ``{"api_<days>d": total_mm}``;
        empty dict on terminal failure (degraded).
        """
        lon, lat = _bbox_centroid(bbox)
        end = as_of
        start = end - timedelta(days=days - 1)
        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "precipitation_sum",
            "timezone": "UTC",
        }

        log.info(
            "openmeteo.api.fetch",
            aoi_id=aoi_id,
            lon=lon,
            lat=lat,
            days=days,
            as_of=as_of.isoformat(),
        )
        try:
            resp = await fetch_with_retry(
                "GET", ARCHIVE_URL, client=await self._client(), params=params
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="openmeteo.api",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return {}

        payload = resp.json()
        daily = payload.get("daily") or {}
        precips = list(daily.get("precipitation_sum") or [])
        total = float(sum(p for p in precips if p is not None))
        return {f"api_{days}d": total}

    async def get_rainfall_grid(
        self,
        *,
        nodes: list[tuple[float, float]],
        window_start: datetime,
        window_end: datetime,
        batch_size: int = 100,
    ) -> list[list[WeatherSample]]:
        """Hourly ERA5-archive precipitation for many ``(lon, lat)`` nodes.

        Returns one hourly precipitation series per input node, in the same
        order. Nodes that fail to fetch degrade to an empty series (never
        raises). Used by the backtest to give each grid cell the rainfall of
        its nearest node instead of a single AOI-centroid series.
        """
        out: list[list[WeatherSample]] = []
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i : i + batch_size]
            params: dict[str, Any] = {
                "latitude": ",".join(f"{lat:.4f}" for _, lat in batch),
                "longitude": ",".join(f"{lon:.4f}" for lon, _ in batch),
                "hourly": "precipitation",
                "start_date": window_start.date().isoformat(),
                "end_date": window_end.date().isoformat(),
                "timezone": "UTC",
            }
            try:
                resp = await fetch_with_retry(
                    "GET", ARCHIVE_URL, client=await self._client(), params=params
                )
            except _DEGRADATION_EXC as exc:
                log.warning("integration.degraded", label="openmeteo.rainfall_grid", error=str(exc))
                out.extend([] for _ in batch)
                continue
            payload = resp.json()
            # A single-node request returns an object, not a list.
            results = payload if isinstance(payload, list) else [payload]
            for node_payload in results:
                out.append(_parse_hourly(node_payload))
        return out
