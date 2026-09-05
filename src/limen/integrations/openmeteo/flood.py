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

    async def _get_many(self, url: str, params: dict[str, Any], label: str) -> list[dict[str, Any]]:
        """A multi-coordinate request. Open-Meteo answers with a JSON **array**.

        Separate from :meth:`_get`, which narrows to ``dict`` and would drop
        the whole response on the floor.
        """
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client(), params=params)
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded", label=label, error=str(exc), error_type=type(exc).__name__
            )
            return []
        payload = resp.json()
        if isinstance(payload, list):
            return [p for p in payload if isinstance(p, dict)]
        return [payload] if isinstance(payload, dict) else []

    async def fetch_signals(
        self,
        *,
        bbox: tuple[float, float, float, float],
        valuation_time: datetime,
        horizon_hours: int = 72,
        basin_max: bool = False,
    ) -> FloodSignals:
        """The three signals for an AOI.

        ``basin_max`` changes only the fluvial term, and exists because the
        centroid of a region almost never sits on a river GloFAS models: a
        measurement there reads 0 or nothing, which is fine as an optional
        bonus to the landslide H component and useless as one of the two
        triggers of the flood hazard.

        Off by default **on purpose**: the landslide champion has been scored
        with the centroid signal, and changing it under the same name would
        move V1's numbers without a backtest.
        """
        lon, lat = _centroid(bbox)
        fluvial = (
            await self._fluvial_basin_max(bbox) if basin_max else await self._fluvial(lon, lat)
        )
        return FloodSignals(
            rain_72h_mm=await self._pluvial(lon, lat, valuation_time, horizon_hours),
            river_discharge_ratio=fluvial,
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

    async def _fluvial_basin_max(
        self,
        bbox: tuple[float, float, float, float],
        *,
        spacing: float = 0.25,
        min_baseline_fraction: float = 0.1,
    ) -> float | None:
        """The worst discharge ratio among the AOI's *real* rivers, in one request.

        Probes a lattice over the bbox. "Is the region's main river in flood?"
        is the question a basin-scale signal can honestly answer; the per-cell
        answer needs river points joined to the grid at bootstrap, which is a
        heavier job and belongs with EFAS.

        The ratio is pathological on trickles: a watercourse averaging 0.01
        m³/s that peaks at 0.6 scores 62, and a plain maximum over the lattice
        picks exactly those. Measured on Basilicata: max-over-everything gave
        62.0, which is a ditch, not a flood. So only points whose trailing
        baseline is at least ``min_baseline_fraction`` of the AOI's largest
        count as rivers -- keeping tributaries, dropping ditches.

        ``None`` when no probe finds a river: an AOI with no modelled
        watercourse has no fluvial risk, which is different from a river
        running low.
        """
        from limen.integrations.openmeteo.grid import build_snapped_nodes

        nodes = build_snapped_nodes(bbox, spacing=spacing)
        results = await self._get_many(
            FLOOD_URL,
            {
                "latitude": ",".join(f"{lat:.4f}" for _, lat in nodes),
                "longitude": ",".join(f"{lon:.4f}" for lon, _ in nodes),
                "daily": "river_discharge",
                "past_days": 31,
                "forecast_days": 7,
                "timezone": "UTC",
            },
            "openmeteo.flood.fluvial_basin",
        )
        measured: list[tuple[float, float]] = []  # (baseline, ratio)
        for point in results:
            vals = _floats((point.get("daily") or {}).get("river_discharge"))
            if len(vals) < 8:
                continue
            past, future = vals[:-7], vals[-7:]
            baseline = sum(past) / len(past) if past else 0.0
            if baseline <= 0.0 or not future:
                continue
            measured.append((baseline, max(future) / baseline))
        if not measured:
            return None
        floor = max(b for b, _ in measured) * min_baseline_fraction
        rivers = [ratio for baseline, ratio in measured if baseline >= floor]
        return max(rivers) if rivers else None

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
