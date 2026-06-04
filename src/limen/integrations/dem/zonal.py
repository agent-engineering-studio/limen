"""Zonal statistics — per-cell aggregates over a DEM + its derivatives.

For each grid cell we compute mean elevation, slope, aspect-bearing-
ignoring (compass aspect doesn't average linearly, so we report the
*median* aspect over non-flat pixels) and curvature. The cell polygon
is reprojected into the raster's CRS before masking; this keeps the
operational DB at EPSG:4326 while the upstream raster stays in
whatever projection it ships with (TINITALY is in ETRS89 / UTM 32N).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.integrations.dem.derivatives import aspect_deg, curvature, slope_deg

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellDemStats:
    """Per-cell aggregate the static-bootstrap pipeline upserts."""

    cell_id: str
    elevation_m: float | None
    slope_deg: float | None
    aspect_deg: float | None
    curvature: float | None
    pixel_count: int


def _reproject_geom(geom: BaseGeometry, *, src_crs: Any, dst_crs: Any) -> BaseGeometry:
    """Reproject a shapely geometry from EPSG:4326 to the raster's CRS."""
    if src_crs == dst_crs:
        return geom
    try:
        from pyproj import Transformer
        from shapely.ops import transform
    except ImportError as exc:  # pragma: no cover — pyproj ships with rasterio
        raise RuntimeError("pyproj required for DEM zonal stats") from exc

    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform(transformer.transform, geom)


def _cellsize_from_transform(transform: Any) -> float:
    """Approximate the raster's metric cell size from its affine transform.

    For a square grid in a metric CRS (UTM / Lambert), ``abs(a)`` is the
    pixel width in metres. For a geographic CRS we'd need a per-row
    correction; the project doc requires TINITALY-style metric DEMs so
    we keep it simple here and let callers pass an override.
    """
    return float(abs(transform.a))


def compute_cell_stats(
    *,
    raster_path: Path,
    cells: dict[str, BaseGeometry],
    src_crs_epsg: int = 4326,
    cellsize_override: float | None = None,
) -> list[CellDemStats]:
    """Read the DEM at ``raster_path`` and return per-cell stats.

    ``cells`` maps ``cell_id`` → polygon in EPSG:4326. The function
    reprojects each polygon into the raster's CRS, masks the raster to
    that polygon, computes the derivatives once (per chunk), and
    aggregates pixel-wise. Cells with zero usable pixels get NULL
    fields + ``pixel_count=0`` so the caller can decide whether to
    upsert them.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.mask import mask as raster_mask
    except ImportError as exc:  # pragma: no cover — rasterio is in core deps
        raise RuntimeError("rasterio required for DEM zonal stats") from exc

    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"DEM raster not found: {path}")

    out: list[CellDemStats] = []
    with rasterio.open(path) as src:
        cellsize = cellsize_override or _cellsize_from_transform(src.transform)
        if cellsize <= 0:
            raise ValueError(f"non-positive cellsize derived from raster: {cellsize}")

        from rasterio.crs import CRS as _CRS

        src_crs = _CRS.from_epsg(src_crs_epsg)
        for cell_id, geom in cells.items():
            projected = _reproject_geom(geom, src_crs=src_crs, dst_crs=src.crs)
            try:
                data, _ = raster_mask(src, [projected], crop=True, filled=False)
            except (ValueError, Exception) as exc:  # pragma: no cover — rasterio errors
                _log.warning(
                    "dem.zonal.cell_skip",
                    cell_id=cell_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                out.append(_empty_stats(cell_id))
                continue

            band = data[0].astype(np.float32, copy=False)
            mask = np.ma.getmaskarray(band) if isinstance(band, np.ma.MaskedArray) else None
            arr = np.where(mask, np.nan, band) if mask is not None else band
            n_valid = int(np.count_nonzero(~np.isnan(arr)))
            if n_valid == 0:
                out.append(_empty_stats(cell_id))
                continue

            elev_mean = float(np.nanmean(arr))
            slope_arr = slope_deg(arr, cellsize=cellsize)
            slope_mean = float(np.nanmean(slope_arr))
            aspect_arr = aspect_deg(arr, cellsize=cellsize)
            aspect_valid = aspect_arr[(aspect_arr >= 0.0) & ~np.isnan(aspect_arr)]
            aspect_median = float(np.median(aspect_valid)) if aspect_valid.size else None
            curv_arr = curvature(arr, cellsize=cellsize)
            curv_mean = float(np.nanmean(curv_arr))

            out.append(
                CellDemStats(
                    cell_id=cell_id,
                    elevation_m=elev_mean,
                    slope_deg=slope_mean,
                    aspect_deg=aspect_median,
                    curvature=curv_mean,
                    pixel_count=n_valid,
                )
            )
    _log.info(
        "dem.zonal.done",
        raster=str(path),
        cells_in=len(cells),
        cells_with_data=sum(1 for s in out if s.pixel_count > 0),
    )
    return out


def _empty_stats(cell_id: str) -> CellDemStats:
    return CellDemStats(
        cell_id=cell_id,
        elevation_m=None,
        slope_deg=None,
        aspect_deg=None,
        curvature=None,
        pixel_count=0,
    )


__all__ = ["CellDemStats", "compute_cell_stats"]
