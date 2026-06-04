"""DEM zonal stats — synthetic GeoTIFF + a polygon, verify per-cell aggregates."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import Polygon

from limen.integrations.dem.zonal import compute_cell_stats

pytestmark = pytest.mark.integration


def _write_synthetic_dem(
    path: Path,
    *,
    width: int = 50,
    height: int = 50,
    gradient_m: float = 1.0,
    origin_x: float = 500_000.0,
    origin_y: float = 4_550_000.0,
    cellsize: float = 10.0,
) -> None:
    """Write a small GeoTIFF in EPSG:32633 (UTM 33N — covers southern Italy).

    Each column is ``gradient_m`` higher than the previous one so the
    analytical slope is constant and easy to assert against. The CRS is
    metric, which matches what TINITALY ships.
    """
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    x = np.arange(width, dtype=np.float32)
    band = np.tile(x * gradient_m, (height, 1))
    transform = from_origin(origin_x, origin_y, cellsize, cellsize)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs="EPSG:32633",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.write(band, 1)


def _utm_to_wgs84_polygon(
    *,
    origin_x: float,
    origin_y: float,
    width_cells: int,
    height_cells: int,
    cellsize: float,
) -> Polygon:
    """Reproject the GeoTIFF's interior bbox into EPSG:4326 polygon."""
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:32633", "EPSG:4326", always_xy=True)
    # Take the interior so we don't sit on the edge of the raster.
    min_x = origin_x + cellsize
    max_x = origin_x + (width_cells - 1) * cellsize
    min_y = origin_y - (height_cells - 1) * cellsize
    max_y = origin_y - cellsize
    corners = [
        transformer.transform(min_x, min_y),
        transformer.transform(max_x, min_y),
        transformer.transform(max_x, max_y),
        transformer.transform(min_x, max_y),
    ]
    return Polygon([*corners, corners[0]])


def test_compute_cell_stats_returns_consistent_aggregates(tmp_path: Path) -> None:
    raster = tmp_path / "synthetic_dem.tif"
    _write_synthetic_dem(
        raster,
        width=50,
        height=50,
        gradient_m=1.0,
        origin_x=500_000.0,
        origin_y=4_550_000.0,
        cellsize=10.0,
    )
    cell = _utm_to_wgs84_polygon(
        origin_x=500_000.0,
        origin_y=4_550_000.0,
        width_cells=50,
        height_cells=50,
        cellsize=10.0,
    )

    stats = compute_cell_stats(raster_path=raster, cells={"c-1": cell})
    assert len(stats) == 1
    s = stats[0]
    assert s.cell_id == "c-1"
    assert s.pixel_count > 100  # the cell covers most of the synthetic raster
    # Mean elevation = mean column * gradient = (0+1+...+49)/50 = 24.5
    # The reprojected polygon trims the edges so we accept a small spread.
    assert s.elevation_m is not None
    assert 15.0 < s.elevation_m < 35.0
    # Slope is constant ≈ atan(0.1) ≈ 5.71°.
    assert s.slope_deg is not None
    assert 5.0 < s.slope_deg < 6.5
    # Aspect points east (uphill) for this DEM — UTM33N axes match
    # geographic east/north up to a small convergence angle.
    assert s.aspect_deg is not None
    assert 60.0 < s.aspect_deg < 120.0


def test_compute_cell_stats_empty_when_cell_outside_raster(tmp_path: Path) -> None:
    raster = tmp_path / "synthetic_dem.tif"
    _write_synthetic_dem(raster)
    # A polygon far to the north of the synthetic raster.
    far_cell = Polygon([(8.0, 50.0), (8.1, 50.0), (8.1, 50.1), (8.0, 50.1), (8.0, 50.0)])
    stats = compute_cell_stats(raster_path=raster, cells={"c-far": far_cell})
    assert len(stats) == 1
    assert stats[0].pixel_count == 0
    assert stats[0].elevation_m is None


def test_compute_cell_stats_missing_raster_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_cell_stats(
            raster_path=tmp_path / "no-such-raster.tif",
            cells={"c": Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])},
        )
