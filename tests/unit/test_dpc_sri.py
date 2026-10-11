"""Unit checks for the DPC SRI grid sampling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS

from limen.integrations.dpc import SriGrid


def _grid() -> SriGrid:
    """10x10 EPSG:4326 grid over lon 10→11, lat 44→45 (0.1° pixels)."""
    data = np.full((10, 10), 0.5, dtype=np.float32)
    data[2:4, 3:6] = 35.0  # convective blob: 6 hot pixels
    data[0, 0] = -9999.0  # nodata sentinel
    transform = rasterio.Affine(0.1, 0, 10.0, 0, -0.1, 45.0)
    return SriGrid(
        data=data,
        transform=transform,
        crs=CRS.from_epsg(4326),
        observed_at=datetime(2026, 7, 6, 12, 0, tzinfo=UTC),
    )


def test_blob_detected_inside_bbox() -> None:
    peak, hot = _grid().max_intensity((10.0, 44.0, 11.0, 45.0), threshold_mmh=30.0)
    assert peak == 35.0
    assert hot == 6


def test_quiet_bbox_has_no_trigger() -> None:
    peak, hot = _grid().max_intensity((10.0, 44.0, 10.2, 44.2), threshold_mmh=30.0)
    assert peak == 0.5
    assert hot == 0


def test_out_of_coverage_returns_zero() -> None:
    peak, hot = _grid().max_intensity((20.0, 50.0, 21.0, 51.0), threshold_mmh=30.0)
    assert (peak, hot) == (0.0, 0)


def test_nodata_is_ignored() -> None:
    peak, _ = _grid().max_intensity((10.0, 44.8, 10.2, 45.0), threshold_mmh=30.0)
    assert peak >= 0.0


def test_sample_reads_the_median_of_the_window_not_the_pixel() -> None:
    """Un pixel spurio non allaga una cella (#199): l'11 ottobre 2026 il
    Merging aveva 7.348 mm in 24 ore su un pixel solo."""
    g = _grid()
    g.data[7, 7] = 7348.0
    centro = (10.75, 44.25)  # pixel (7, 7)
    blob = (10.45, 44.75)  # pixel (2, 4), dentro il blob
    assert g.sample([centro, blob]) == [0.5, 35.0]


def test_sample_outside_or_on_nodata_is_not_measured() -> None:
    g = _grid()
    g.data[:3, :3] = -9999.0
    assert g.sample([(20.0, 50.0), (10.05, 44.95)]) == [None, None]
    assert g.sample([]) == []


async def test_a_cumulative_frame_is_downloaded_once_per_issue(monkeypatch: Any) -> None:
    """Venti regioni chiedono lo stesso file nazionale: si riscarica solo
    quando il DPC ne pubblica uno nuovo."""
    from limen.integrations.dpc import client

    visti: list[SriGrid | None] = []

    async def _download(tipo: str, cached: SriGrid | None = None) -> SriGrid | None:
        assert tipo == "CUM24"
        visti.append(cached)
        return cached or _grid()

    monkeypatch.setattr(client, "_download", _download)
    monkeypatch.setattr(client, "_cum_cache", {})
    primo = await client.get_latest_cum(24)
    secondo = await client.get_latest_cum(24)
    assert visti == [None, primo]
    assert secondo is primo
