"""NASA FIRMS active-fire hotspot client (Area CSV API).

FIRMS publishes VIIRS 375 m (S-NPP, NOAA-20, NOAA-21) and MODIS 1 km
active-fire detections with ~3 h NRT latency:

    GET /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{1..5}[/{YYYY-MM-DD}]

One national bbox costs one transaction per source against a quota of
5000 per 10 minutes, so the whole of Italy is a rounding error.

Quality filter: FIRMS is a detection feed, not a fire inventory —
industrial flares, sun glint and hot bare soil show up as
low-confidence pixels. We drop them at parse time (thresholds from
settings, never hard-coded); the persistence requirement of several
detections before an AOI is acted on lives in the caller.

Degradation: any terminal failure on a source yields no detections for
that source plus an ``integration.degraded`` log line — the other
sources still contribute and the caller never sees an exception.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import TYPE_CHECKING, Literal

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.data.repos.fire_repo import FireHotspot
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Sequence

log = get_logger(__name__)

DEFAULT_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)

ConfidenceLevel = Literal["low", "nominal", "high"]

# VIIRS reports single letters in the NRT products and full words in the
# standard ones; MODIS reports a 0..100 percentage instead.
_VIIRS_CONFIDENCE: dict[str, ConfidenceLevel] = {
    "l": "low",
    "low": "low",
    "n": "nominal",
    "nominal": "nominal",
    "h": "high",
    "high": "high",
}
_CONFIDENCE_RANK: dict[ConfidenceLevel, int] = {"low": 0, "nominal": 1, "high": 2}


def _passes_confidence(raw: str | None, *, min_level: ConfidenceLevel, min_pct: int) -> bool:
    """Quality gate over either confidence encoding.

    An unparseable / missing value is kept: MODIS SP rows occasionally
    omit it, and dropping a real fire is worse than keeping a doubtful
    pixel that still has to cluster with others to matter.
    """
    if raw is None:
        return True
    token = raw.strip().lower()
    if not token:
        return True
    level = _VIIRS_CONFIDENCE.get(token)
    if level is not None:
        return _CONFIDENCE_RANK[level] >= _CONFIDENCE_RANK[min_level]
    try:
        return int(float(token)) >= min_pct
    except ValueError:
        return True


def _as_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_row(row: dict[str, str], *, source: str) -> FireHotspot | None:
    lat = _as_float(row.get("latitude"))
    lon = _as_float(row.get("longitude"))
    if lat is None or lon is None:
        return None
    try:
        acq_date = date.fromisoformat((row.get("acq_date") or "").strip()[:10])
    except ValueError:
        return None
    try:
        acq_time = int((row.get("acq_time") or "").strip())
    except ValueError:
        return None
    if not 0 <= acq_time <= 2359:
        return None

    confidence = (row.get("confidence") or "").strip() or None
    # VIIRS names the 4 µm channel bright_ti4, MODIS calls it brightness.
    brightness = _as_float(row.get("bright_ti4")) or _as_float(row.get("brightness"))
    return FireHotspot(
        source=source,
        acq_date=acq_date,
        acq_time=acq_time,
        latitude=lat,
        longitude=lon,
        frp_mw=_as_float(row.get("frp")),
        confidence=confidence,
        brightness_k=brightness,
        daynight=(row.get("daynight") or "").strip() or None,
        satellite=(row.get("satellite") or "").strip() or None,
        instrument=(row.get("instrument") or "").strip() or None,
    )


def parse_hotspot_csv(
    payload: str,
    *,
    source: str,
    min_confidence: ConfidenceLevel = "nominal",
    min_confidence_pct: int = 50,
    min_frp_mw: float = 0.0,
) -> list[FireHotspot]:
    """Parse a FIRMS CSV response, dropping rows below the quality bar."""
    hotspots: list[FireHotspot] = []
    dropped = 0
    for row in csv.DictReader(io.StringIO(payload)):
        clean: dict[str, str] = {
            str(k).strip().lower(): str(v) if v is not None else "" for k, v in row.items()
        }
        hotspot = _parse_row(clean, source=source)
        if hotspot is None:
            dropped += 1
            continue
        if not _passes_confidence(
            hotspot.confidence, min_level=min_confidence, min_pct=min_confidence_pct
        ):
            dropped += 1
            continue
        if min_frp_mw > 0.0 and (hotspot.frp_mw is None or hotspot.frp_mw < min_frp_mw):
            dropped += 1
            continue
        hotspots.append(hotspot)
    if dropped:
        log.info("firms.hotspots.filtered", source=source, kept=len(hotspots), dropped=dropped)
    return hotspots


class FirmsHttpClient:
    """Concrete :class:`FirmsClient` Protocol implementation."""

    def __init__(
        self,
        *,
        map_key: str,
        base_url: str = DEFAULT_BASE_URL,
        min_confidence: ConfidenceLevel = "nominal",
        min_confidence_pct: int = 50,
        min_frp_mw: float = 0.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._map_key = map_key
        self._base_url = base_url.rstrip("/")
        self._min_confidence = min_confidence
        self._min_confidence_pct = min_confidence_pct
        self._min_frp_mw = min_frp_mw
        self._http = http_client

    async def _client(self) -> httpx.AsyncClient:
        return self._http if self._http is not None else await SharedHttpClient.get()

    def _url(
        self,
        *,
        source: str,
        bbox: tuple[float, float, float, float],
        day_range: int,
        on_date: date | None,
    ) -> str:
        area = ",".join(f"{c:g}" for c in bbox)
        url = f"{self._base_url}/{self._map_key}/{source}/{area}/{day_range}"
        return f"{url}/{on_date.isoformat()}" if on_date is not None else url

    async def fetch_hotspots(
        self,
        *,
        bbox: tuple[float, float, float, float],
        sources: Sequence[str],
        day_range: int = 1,
        on_date: date | None = None,
    ) -> list[FireHotspot]:
        """Return quality-filtered detections across ``sources``.

        A source that fails contributes nothing; the rest still count.
        """
        out: list[FireHotspot] = []
        for source in sources:
            payload = await self._fetch_source(
                source=source, bbox=bbox, day_range=day_range, on_date=on_date
            )
            if payload is None:
                continue
            out.extend(
                parse_hotspot_csv(
                    payload,
                    source=source,
                    min_confidence=self._min_confidence,
                    min_confidence_pct=self._min_confidence_pct,
                    min_frp_mw=self._min_frp_mw,
                )
            )
        log.info("firms.hotspots.fetched", count=len(out), sources=list(sources))
        return out

    async def _fetch_source(
        self,
        *,
        source: str,
        bbox: tuple[float, float, float, float],
        day_range: int,
        on_date: date | None,
    ) -> str | None:
        url = self._url(source=source, bbox=bbox, day_range=day_range, on_date=on_date)
        log.info("firms.hotspots.fetch", source=source, bbox=bbox, day_range=day_range)
        try:
            resp = await fetch_with_retry("GET", url, client=await self._client())
        except _DEGRADATION_EXC as exc:
            log.warning(
                "integration.degraded",
                label="firms.hotspots",
                source=source,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None
        if resp.status_code >= 400 or not resp.content:
            # 401 = bad MAP_KEY, 429 = quota exhausted after retries.
            log.warning("firms.hotspots.no_data", source=source, status=resp.status_code)
            return None
        return resp.text
