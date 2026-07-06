"""DPC national radar — SRI (Surface Rainfall Intensity) client.

Open data of the Dipartimento della Protezione Civile radar platform
(https://radar-api.protezionecivile.it, CC-BY-SA 4.0). The SRI product is
a national 1 km GeoTIFF in mm/h refreshed every 5 minutes — the trigger
signal for the nowcast job: radar decides *when* to run, the existing
scoring pipeline decides *what* to alert.

Read-only integration: every failure degrades to ``None`` and logs
``integration.degraded`` — it never raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

RADAR_API = "https://radar-api.protezionecivile.it"
# The API rejects requests without an `origin` header.
_HEADERS = {"origin": "https://radar.protezionecivile.gov.it"}
_NODATA = -9999.0

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
    """One national SRI frame: mm/h on a 1 km grid."""

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


async def get_latest_sri() -> SriGrid | None:
    """Fetch + parse the most recent national SRI frame (None on failure)."""
    client = await SharedHttpClient.get()
    try:
        resp = await fetch_with_retry(
            "GET",
            f"{RADAR_API}/findLastProductByType",
            client=client,
            params={"type": "SRI"},
            headers=_HEADERS,
        )
        payload: dict[str, Any] = resp.json()
        product = payload["lastProducts"][0]
        product_time = int(product["time"])

        resp = await fetch_with_retry(
            "POST",
            f"{RADAR_API}/downloadProduct",
            client=client,
            json={"productType": "SRI", "productDate": product_time},
            headers=_HEADERS,
        )
        url = str(resp.json()["url"])
        resp = await fetch_with_retry("GET", url, client=client)
        raw = resp.content
    except _DEGRADATION_EXC as exc:
        log.warning(
            "integration.degraded",
            label="dpc.sri",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
    except IndexError:
        log.warning("integration.degraded", label="dpc.sri", error="no products available")
        return None

    with MemoryFile(raw) as mem, mem.open() as ds:
        grid = SriGrid(
            data=ds.read(1),
            transform=ds.transform,
            crs=ds.crs,
            observed_at=datetime.fromtimestamp(product_time / 1000, tz=UTC),
        )
    log.info(
        "dpc.sri.fetched",
        observed_at=grid.observed_at.isoformat(),
        shape=grid.data.shape,
    )
    return grid


__all__ = ["SriGrid", "get_latest_sri"]
