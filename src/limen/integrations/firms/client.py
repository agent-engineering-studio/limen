"""NASA FIRMS active-fire hotspot client (Area CSV API).

FIRMS publishes VIIRS 375 m (S-NPP, NOAA-20, NOAA-21) and MODIS 1 km
active-fire detections with ~3 h NRT latency:

    GET /api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{1..5}[/{YYYY-MM-DD}]

One national bbox costs one transaction per source against a quota of
5000 per 10 minutes, so the whole of Italy is a rounding error.

Parsing, the confidence gate and the area URL come from the
``firms-client`` package (extracted from Limen, Apache-2.0); the shared
retry and the degradation stay here.

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
from typing import TYPE_CHECKING

import httpx
from firms_client import ConfidenceLevel as ConfidenceLevel
from firms_client import area_url, parse_csv, select
from firms_client.sources import AREA_API_BASE
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.data.repos.fire_repo import FireHotspot
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from firms_client import StaticMask

log = get_logger(__name__)

DEFAULT_BASE_URL = AREA_API_BASE

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


def parse_hotspot_csv(
    payload: str,
    *,
    source: str,
    min_confidence: ConfidenceLevel = "nominal",
    min_confidence_pct: int = 50,
    min_frp_mw: float = 0.0,
    static_mask: StaticMask | None = None,
) -> list[FireHotspot]:
    """Parse a FIRMS CSV response, dropping rows below the quality bar.

    Parsing and the confidence/FRP gate come from ``firms-client``. The
    ``type`` filter (vegetation vs industry) is *not* applied here: the
    column is stored, and the consumers that need fires only filter on it.

    The area API (NRT) has no ``type`` column, so without ``static_mask``
    the ILVA, the refineries and Etna arrive as ``NULL`` like any wildfire.
    The mask, learned from the archives, gives those rows the ``type`` of
    the static cell they fall in; rows that already carry one are untouched.
    """
    rows = parse_csv(payload)
    if static_mask is not None:
        rows = static_mask.label(rows)
    kept = select(
        rows,
        vegetation_only=False,
        min_confidence=min_confidence,
        min_confidence_pct=min_confidence_pct,
        min_frp_mw=min_frp_mw,
    )
    # Le righe malformate le scarta già parse_csv: si contano dal CSV, o un
    # formato cambiato darebbe meno hotspot senza una riga di log.
    total = sum(1 for _ in csv.DictReader(io.StringIO(payload)))
    if len(kept) < total:
        log.info(
            "firms.hotspots.filtered", source=source, kept=len(kept), dropped=total - len(kept)
        )
    return [
        FireHotspot(
            source=source,
            acq_date=h.acq_date,
            acq_time=h.acq_time,
            latitude=h.latitude,
            longitude=h.longitude,
            frp_mw=h.frp_mw,
            confidence=h.confidence,
            brightness_k=h.brightness_k,
            daynight=h.daynight,
            satellite=h.satellite,
            instrument=h.instrument,
            detection_type=h.detection_type,
        )
        for h in kept
    ]


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
        static_mask: StaticMask | None = None,
    ) -> None:
        self._map_key = map_key
        self._static_mask = static_mask
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
        url = area_url(self._map_key, source, bbox, days=day_range, on_date=on_date)
        if not url.startswith(AREA_API_BASE):
            raise ValueError(f"firms-client built an unexpected area URL: {url}")
        return self._base_url + url[len(AREA_API_BASE) :]

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
                    static_mask=self._static_mask,
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
