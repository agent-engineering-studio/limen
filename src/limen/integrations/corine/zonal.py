"""CORINE Land Cover — per-cell dominant class via majority filter.

Reads the categorical raster, reprojects each cell polygon into the
raster's CRS, masks the raster to the cell, and returns the most-
frequent valid code. ``pixel_count`` distinguishes "no coverage" from
"sparse coverage" so the caller can decide whether to upsert.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellLandUseStats:
    cell_id: str
    landuse_code: str | None
    pixel_count: int


def _reproject_geom(geom: BaseGeometry, *, src_crs: Any, dst_crs: Any) -> BaseGeometry:
    if src_crs == dst_crs:
        return geom
    from pyproj import Transformer
    from shapely.ops import transform

    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    return transform(transformer.transform, geom)


def _majority_class(values: Any, *, nodata: float | None) -> tuple[str | None, int]:
    """Return ``(majority_code_as_str, valid_pixel_count)``.

    Values equal to ``nodata`` (or NaN) are excluded; ties resolve to
    the smallest code (deterministic).
    """
    import numpy as np

    arr = values.ravel()
    if arr.dtype.kind == "f":
        finite = arr[np.isfinite(arr)]
        if nodata is not None:
            finite = finite[finite != nodata]
    else:
        finite = arr if nodata is None else arr[arr != nodata]
    if finite.size == 0:
        return None, 0
    classes, counts = np.unique(finite, return_counts=True)
    # Tie-breaker: highest count first, then smallest code.
    best_idx = int(np.lexsort((classes, -counts))[0])
    return str(int(classes[best_idx])), int(finite.size)


def compute_landuse_stats(
    *,
    raster_path: Path,
    cells: dict[str, BaseGeometry],
    src_crs_epsg: int = 4326,
) -> list[CellLandUseStats]:
    """Compute the dominant CORINE class per cell."""
    try:
        import rasterio
        from rasterio.crs import CRS as _CRS
        from rasterio.mask import mask as raster_mask
    except ImportError as exc:  # pragma: no cover — rasterio is in core deps
        raise RuntimeError("rasterio required for CORINE zonal stats") from exc

    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"CORINE raster not found: {path}")

    out: list[CellLandUseStats] = []
    with rasterio.open(path) as src:
        nodata = src.nodata
        src_crs = _CRS.from_epsg(src_crs_epsg)
        for cell_id, geom in cells.items():
            projected = _reproject_geom(geom, src_crs=src_crs, dst_crs=src.crs)
            try:
                data, _ = raster_mask(src, [projected], crop=True, filled=False)
            except Exception as exc:  # pragma: no cover
                _log.warning(
                    "corine.zonal.cell_skip",
                    cell_id=cell_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                out.append(CellLandUseStats(cell_id=cell_id, landuse_code=None, pixel_count=0))
                continue

            import numpy as np

            band = data[0]
            mask = np.ma.getmaskarray(band) if isinstance(band, np.ma.MaskedArray) else None
            if mask is not None:
                band = np.where(mask, nodata if nodata is not None else -1, band)
            code, n = _majority_class(band, nodata=nodata)
            out.append(CellLandUseStats(cell_id=cell_id, landuse_code=code, pixel_count=n))

    _log.info(
        "corine.zonal.done",
        raster=str(path),
        cells_in=len(cells),
        cells_with_data=sum(1 for s in out if s.pixel_count > 0),
    )
    return out


__all__ = ["CellLandUseStats", "compute_landuse_stats"]
