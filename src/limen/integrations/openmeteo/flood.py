"""Open-Meteo dedicated flood/marine signals (issue #8).

Three forward-looking signals for the dynamic flood factor, each degrading to
``None`` independently (neutral degradation — never raises on a read):

* **pluvial** — forecast 72 h cumulated rain (forecast API);
* **fluvial** — peak river discharge / recent-mean ratio (Flood API, GloFAS);
* **coastal** — normalised wave height (Marine API; ``None`` inland).

These are combined with the ISPRA static hydraulic hazard by the pure scoring
factor in :mod:`limen.core.scoring.flood_forecast`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

# Wave height (m) mapped to the maximal coastal signal (1.0).
_WAVE_REF_M = 4.0

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


@dataclass(frozen=True, slots=True)
class FloodSignals:
    rain_72h_mm: float | None = None
    river_discharge_ratio: float | None = None
    coastal_surge_norm: float | None = None


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    return ((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0)


def _floats(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    return [float(v) for v in values if v is not None]


class OpenMeteoFloodClient:
    """Fetches the dedicated flood/marine signals. All methods degrade to None."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    async def _get(self, url: str, params: dict[str, Any], label: str) -> dict[str, Any] | None:
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client(), params=params)
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded", label=label, error=str(exc), error_type=type(exc).__name__
            )
            return None
        payload = resp.json()
        return payload if isinstance(payload, dict) else None

    async def fetch_signals(
        self,
        *,
        bbox: tuple[float, float, float, float],
        valuation_time: datetime,
        horizon_hours: int = 72,
    ) -> FloodSignals:
        lon, lat = _centroid(bbox)
        return FloodSignals(
            rain_72h_mm=await self._pluvial(lon, lat, valuation_time, horizon_hours),
            river_discharge_ratio=await self._fluvial(lon, lat),
            coastal_surge_norm=await self._coastal(lon, lat),
        )

    async def _pluvial(
        self, lon: float, lat: float, t0: datetime, horizon_hours: int
    ) -> float | None:
        end = (t0 + timedelta(hours=horizon_hours)).date()
        payload = await self._get(
            FORECAST_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "precipitation",
                "start_date": t0.date().isoformat(),
                "end_date": end.isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.pluvial",
        )
        if payload is None:
            return None
        nums = _floats((payload.get("hourly") or {}).get("precipitation"))
        return sum(nums) if nums else None

    async def _fluvial(self, lon: float, lat: float) -> float | None:
        """GloFAS: peak forecast discharge (next 7 d) / recent normal (past ~30 d)."""
        payload = await self._get(
            FLOOD_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "daily": "river_discharge",
                "past_days": 31,
                "forecast_days": 7,
                "timezone": "UTC",
            },
            "openmeteo.flood.fluvial",
        )
        if payload is None:
            return None
        vals = _floats((payload.get("daily") or {}).get("river_discharge"))
        if len(vals) < 8:
            return None
        past, future = vals[:-7], vals[-7:]
        baseline = sum(past) / len(past) if past else 0.0
        if baseline <= 0.0 or not future:
            return None
        return max(future) / baseline

    async def _coastal(self, lon: float, lat: float) -> float | None:
        """Marine wave height normalised; None for inland points (no marine data)."""
        payload = await self._get(
            MARINE_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "hourly": "wave_height",
                "forecast_days": 3,
                "timezone": "UTC",
            },
            "openmeteo.flood.coastal",
        )
        if payload is None:
            return None
        nums = _floats((payload.get("hourly") or {}).get("wave_height"))
        if not nums:
            return None
        return min(1.0, max(nums) / _WAVE_REF_M)
