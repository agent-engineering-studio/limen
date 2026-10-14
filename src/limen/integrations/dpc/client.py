"""DPC national radar — SRI (Surface Rainfall Intensity) client.

Open data of the Dipartimento della Protezione Civile radar platform
(https://radar-api.protezionecivile.it, CC-BY-SA 4.0). The SRI product is
a national 1 km GeoTIFF in mm/h refreshed every 5 minutes — the trigger
signal for the nowcast job: radar decides *when* to run, the existing
scoring pipeline decides *what* to alert.

The CUM products (``CUM3``/``6``/``12``/``24``) are the rain already fallen:
the «Merging» of radar and rain gauges, 0.01° in EPSG:4326, refreshed every
30 minutes. The flood engine reads them as the observed part of its pluvial
window (#199), after checking each frame against the one before it (#235).

Read-only integration: every failure degrades to ``None`` and logs
``integration.degraded`` — it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import rowcol
from rasterio.warp import transform, transform_bounds
from rasterio.windows import from_bounds
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

RADAR_API = "https://radar-api.protezionecivile.it"
# The API rejects requests without an `origin` header.
_HEADERS = {"origin": "https://radar.protezionecivile.gov.it"}
_NODATA = -9999.0
#: Un fotogramma CUM nuovo ogni 30 minuti (`period: PT30M` dell'API).
CUM_PERIOD = timedelta(minutes=30)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
    KeyError,
    ValueError,
)


@dataclass(frozen=True, slots=True)
class SriGrid:
    """One national radar frame: SRI in mm/h, or a CUM accumulation in mm."""

    data: np.ndarray
    transform: rasterio.Affine
    crs: rasterio.crs.CRS
    observed_at: datetime

    def max_intensity(
        self, bbox4326: tuple[float, float, float, float], *, threshold_mmh: float
    ) -> tuple[float, int]:
        """(max mm/h, pixels ≥ threshold) inside a lon/lat bbox.

        Out-of-coverage or all-nodata windows return ``(0.0, 0)``.
        """
        bounds = transform_bounds("EPSG:4326", self.crs, *bbox4326)
        window = from_bounds(*bounds, transform=self.transform)
        row0 = max(0, int(window.row_off))
        col0 = max(0, int(window.col_off))
        row1 = min(self.data.shape[0], int(window.row_off + window.height) + 1)
        col1 = min(self.data.shape[1], int(window.col_off + window.width) + 1)
        if row0 >= row1 or col0 >= col1:
            return 0.0, 0
        tile = self.data[row0:row1, col0:col1]
        valid = tile[tile > _NODATA]
        if valid.size == 0:
            return 0.0, 0
        return float(valid.max()), int((valid >= threshold_mmh).sum())

    def sample(self, points4326: list[tuple[float, float]]) -> list[float | None]:
        """The value at each lon/lat point, as the median of its 3x3 window.

        The median and not the pixel: the Merging product carries isolated
        spikes (7,348 mm in 24 h on one pixel, 11 October 2026) that a single
        read would turn into a flood on one cell. Outside the coverage or on
        an all-nodata window the answer is ``None`` — not measured, not dry.
        """
        if not points4326:
            return []
        xs, ys = transform(
            "EPSG:4326", self.crs, [p[0] for p in points4326], [p[1] for p in points4326]
        )
        rows, cols = rowcol(self.transform, xs, ys)
        h, w = self.data.shape
        out: list[float | None] = []
        for r, c in zip(rows, cols, strict=True):
            if not (0 <= r < h and 0 <= c < w):
                out.append(None)
                continue
            tile = self.data[max(0, r - 1) : r + 2, max(0, c - 1) : c + 2]
            valid = tile[tile > _NODATA]
            out.append(float(np.median(valid)) if valid.size else None)
        return out

    def discard_inconsistent(self, previous: SriGrid, *, max_step: float) -> tuple[SriGrid, int]:
        """This frame without the pixels that moved more than ``max_step``
        since ``previous``, and how many they were.

        Two accumulations over the same duration, one period apart, differ by
        the rain that entered the window minus the rain that left it: never
        more than one period's worth of rain. A pixel that moves further is
        wrong in at least one of the two frames, and which one cannot be told
        from here — so it becomes nodata, «not measured», and the cell falls
        back to the forecast. On 9-11 October 2026 the :30 CUM24 series
        carried 10,047 mm where the :00 series read 28 (#235); the median in
        :meth:`sample` cannot remove a 16 km bump. Frames on different grids
        cannot be compared and come back unchanged.
        """
        if previous.data.shape != self.data.shape or previous.transform != self.transform:
            return self, 0
        a = self.data
        b = previous.data
        bad = (a > _NODATA) & (b > _NODATA) & (np.abs(a - b) > max_step)
        n = int(bad.sum())
        if n == 0:
            return self, 0
        data = a.copy()
        data[bad] = _NODATA
        return replace(self, data=data), n


async def _download(
    product_type: str, cached: SriGrid | None = None, *, at: datetime | None = None
) -> SriGrid | None:
    """The most recent frame of ``product_type`` (or the one issued ``at``);
    ``cached`` if it is still that one."""
    client = await SharedHttpClient.get()
    try:
        if at is None:
            resp = await fetch_with_retry(
                "GET",
                f"{RADAR_API}/findLastProductByType",
                client=client,
                params={"type": product_type},
                headers=_HEADERS,
            )
            payload: dict[str, Any] = resp.json()
            product = payload["lastProducts"][0]
            product_time = int(product["time"])
        else:
            product_time = int(at.timestamp() * 1000)
        observed_at = datetime.fromtimestamp(product_time / 1000, tz=UTC)
        if cached is not None and cached.observed_at == observed_at:
            return cached

        resp = await fetch_with_retry(
            "POST",
            f"{RADAR_API}/downloadProduct",
            client=client,
            json={"productType": product_type, "productDate": product_time},
            headers=_HEADERS,
        )
        url = str(resp.json()["url"])
        resp = await fetch_with_retry("GET", url, client=client)
        raw = resp.content
    except _DEGRADATION_EXC as exc:
        log.warning(
            "integration.degraded",
            label=f"dpc.{product_type.lower()}",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
    except IndexError:
        log.warning(
            "integration.degraded",
            label=f"dpc.{product_type.lower()}",
            error="no products available",
        )
        return None

    with MemoryFile(raw) as mem, mem.open() as ds:
        grid = SriGrid(
            data=ds.read(1),
            transform=ds.transform,
            crs=ds.crs,
            observed_at=observed_at,
        )
    log.info(
        "dpc.radar.fetched",
        product=product_type,
        observed_at=grid.observed_at.isoformat(),
        shape=grid.data.shape,
    )
    return grid


async def get_latest_sri() -> SriGrid | None:
    """Fetch + parse the most recent national SRI frame (None on failure)."""
    return await _download("SRI")


#: L'ultimo fotogramma CUM per durata. Una regione dopo l'altra chiede lo
#: stesso file nazionale (~2 MB, nuovo ogni 30 minuti): si riscarica solo
#: quando il DPC ne pubblica uno nuovo.
_cum_cache: dict[int, SriGrid] = {}
#: Il fotogramma prima dell'ultimo: è quello contro cui si controlla il nuovo
#: (#235), quindi a regime il controllo non scarica niente in più.
_cum_previous: dict[int, SriGrid] = {}


async def get_latest_cum(hours: int) -> SriGrid | None:
    """The most recent national rain accumulation over ``hours`` (None on failure)."""
    old = _cum_cache.get(hours)
    grid = await _download(f"CUM{hours}", old)
    if grid is not None:
        if old is not None and old.observed_at != grid.observed_at:
            _cum_previous[hours] = old
        _cum_cache[hours] = grid
    return grid


async def get_cum_at(hours: int, observed_at: datetime) -> SriGrid | None:
    """The accumulation over ``hours`` issued at ``observed_at`` (None on failure)."""
    for g in (_cum_cache.get(hours), _cum_previous.get(hours)):
        if g is not None and g.observed_at == observed_at:
            return g
    grid = await _download(f"CUM{hours}", at=observed_at)
    if grid is not None:
        _cum_previous[hours] = grid
    return grid


__all__ = ["CUM_PERIOD", "SriGrid", "get_cum_at", "get_latest_cum", "get_latest_sri"]
