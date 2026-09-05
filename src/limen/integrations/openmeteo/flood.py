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

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
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
    #: Per-node signals, present only when ``per_node`` was requested. The
    #: AOI-level scalars above stay for the landslide H component, which has
    #: always used them; the flood hazard reads these, because a single number
    #: copied onto every cell of a region is exactly the failure this repo
    #: already documented for rainfall (13 mm at the Puglia centroid against
    #: 77 mm at the cells that actually failed).
    nodes: tuple[tuple[float, float], ...] = ()
    rain_by_node: tuple[float | None, ...] = ()
    river_ratio_by_node: tuple[float | None, ...] = ()


#: Passo del reticolo su cui i due segnali dell'alluvione sono campionati.
#: Misurato sulla Basilicata: a 0.25° (~25 km) solo 2 nodi su 35 cadono su un
#: corso d'acqua modellato da GloFAS, quindi quasi nessuna cella riceverebbe il
#: segnale fluviale; a 0.1° sono 20 su 176. Più fitto non regge una sola
#: richiesta — 0.05° fa 677 punti e l'API risponde con qualcosa che non è
#: JSON — ed è anche il motivo per cui le richieste vanno a lotti.
_NODE_SPACING_DEG = 0.1

#: Punti per richiesta. Lo stesso limite che usa la griglia di pioggia.
_GRID_BATCH = 100

#: Come la degradazione condivisa, più `ValueError`: una richiesta troppo
#: grande risponde con un corpo che non è JSON, e `resp.json()` alza di lì.
_GRID_DEGRADATION_EXC: tuple[type[BaseException], ...] = (*_DEGRADATION_EXC, ValueError)


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

    async def _get_many(
        self,
        url: str,
        nodes: list[tuple[float, float]],
        params: dict[str, Any],
        label: str,
    ) -> list[dict[str, Any]]:
        """A multi-coordinate request, in batches. Open-Meteo answers with an array.

        Separate from :meth:`_get`, which narrows to ``dict`` and would drop
        the whole response on the floor.

        Batched because the coordinates travel in the query string: 677 points
        came back as something that was not JSON at all. A failed batch
        contributes empty dicts rather than shortening the list, so the
        caller's positional mapping onto nodes stays aligned.
        """
        out: list[dict[str, Any]] = []
        for i in range(0, len(nodes), _GRID_BATCH):
            batch = nodes[i : i + _GRID_BATCH]
            batch_params = {
                **params,
                "latitude": ",".join(f"{lat:.4f}" for _, lat in batch),
                "longitude": ",".join(f"{lon:.4f}" for lon, _ in batch),
            }
            try:
                resp = await fetch_with_retry(
                    "GET", url, client=await self._client(), params=batch_params
                )
                payload = resp.json()
            except _GRID_DEGRADATION_EXC as exc:
                # ValueError copre un corpo che non è JSON: una richiesta
                # sovradimensionata risponde così, e uno sweep deve degradare.
                log.warning(
                    "integration.degraded",
                    label=label,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    batch_size=len(batch),
                )
                out.extend({} for _ in batch)
                continue
            if isinstance(payload, list):
                points: list[dict[str, Any]] = [p if isinstance(p, dict) else {} for p in payload]
            elif isinstance(payload, dict):
                points = [payload]
            else:
                points = []
            if len(points) != len(batch):
                log.warning(
                    "openmeteo.flood.batch_size_mismatch",
                    label=label,
                    expected=len(batch),
                    got=len(points),
                )
                out.extend({} for _ in batch)
                continue
            out.extend(points)
        return out

    async def fetch_signals(
        self,
        *,
        bbox: tuple[float, float, float, float],
        valuation_time: datetime,
        horizon_hours: int = 72,
        per_node: bool = False,
    ) -> FloodSignals:
        """The three AOI-level signals, plus per-node ones when asked.

        ``per_node`` exists because both dynamic signals are useless as a
        single number per region once they *are* the engine. The centroid of
        an AOI almost never sits on a river GloFAS models (measured: 0.0 for
        Basilicata), and a centroid rain reading misses the convective cell
        that actually floods somewhere else.

        Off by default **on purpose**: the landslide champion has been scored
        with the centroid scalars, and changing them under the same names
        would move V1's numbers without a backtest.
        """
        lon, lat = _centroid(bbox)
        signals = FloodSignals(
            rain_72h_mm=await self._pluvial(lon, lat, valuation_time, horizon_hours),
            river_discharge_ratio=await self._fluvial(lon, lat),
            coastal_surge_norm=await self._coastal(lon, lat),
        )
        if not per_node:
            return signals

        from limen.integrations.openmeteo.grid import build_snapped_nodes

        nodes = build_snapped_nodes(bbox, spacing=_NODE_SPACING_DEG)
        rain = await self._pluvial_by_node(nodes, valuation_time, horizon_hours)
        rivers = await self._fluvial_by_node(nodes)
        return replace(
            signals,
            nodes=tuple(nodes),
            rain_by_node=tuple(rain),
            river_ratio_by_node=tuple(rivers),
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

    async def _pluvial_by_node(
        self, nodes: list[tuple[float, float]], t0: datetime, horizon_hours: int
    ) -> list[float | None]:
        """Forecast rain over ``horizon_hours`` at each node, in one request.

        Hour-bounded, not day-bounded: summing whole calendar days from
        ``t0.date()`` would stretch a 72 h window to as much as 96 h, and the
        thresholds it feeds are stated per window.
        """
        end = t0 + timedelta(hours=horizon_hours)
        results = await self._get_many(
            FORECAST_URL,
            nodes,
            {
                "hourly": "precipitation",
                "start_date": t0.date().isoformat(),
                "end_date": end.date().isoformat(),
                "timezone": "UTC",
            },
            "openmeteo.flood.pluvial_grid",
        )
        if len(results) != len(nodes):
            return [None] * len(nodes)
        out: list[float | None] = []
        for point in results:
            hourly = point.get("hourly") or {}
            stamps = hourly.get("time") if isinstance(hourly.get("time"), list) else []
            values = _floats(hourly.get("precipitation"))
            if not stamps or len(values) != len(stamps):
                out.append(sum(values) if values else None)
                continue
            total = 0.0
            seen = False
            for stamp, mm in zip(stamps, values, strict=False):
                when = datetime.fromisoformat(str(stamp))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if t0 <= when <= end:
                    total += mm
                    seen = True
            out.append(total if seen else None)
        return out

    async def _fluvial_by_node(
        self,
        nodes: list[tuple[float, float]],
        *,
        min_baseline_fraction: float = 0.1,
    ) -> list[float | None]:
        """Discharge ratio at each node, ``None`` where there is no river.

        The ratio is pathological on trickles: a watercourse averaging 0.01
        m³/s that peaks at 0.6 scores 62. Measured on Basilicata, a plain
        maximum over the lattice gave 62.0 where the real rivers sat at 1.25.
        So a node counts as carrying a river only if its trailing baseline is
        at least ``min_baseline_fraction`` of the AOI's largest -- keeping
        tributaries, dropping ditches -- and the others report ``None``.

        Per node and not an AOI-wide maximum: one basin in flood must not push
        cells in a different catchment past the alert gate.
        """
        results = await self._get_many(
            FLOOD_URL,
            nodes,
            {
                "daily": "river_discharge",
                "past_days": 31,
                "forecast_days": 7,
                "timezone": "UTC",
            },
            "openmeteo.flood.fluvial_grid",
        )
        if len(results) != len(nodes):
            return [None] * len(nodes)
        measured: list[tuple[float, float] | None] = []
        for point in results:
            vals = _floats((point.get("daily") or {}).get("river_discharge"))
            if len(vals) < 8:
                measured.append(None)
                continue
            past, future = vals[:-7], vals[-7:]
            baseline = sum(past) / len(past) if past else 0.0
            if baseline <= 0.0 or not future:
                measured.append(None)
                continue
            measured.append((baseline, max(future) / baseline))

        baselines = [m[0] for m in measured if m is not None]
        if not baselines:
            return [None] * len(nodes)
        floor = max(baselines) * min_baseline_fraction
        return [m[1] if m is not None and m[0] >= floor else None for m in measured]

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
