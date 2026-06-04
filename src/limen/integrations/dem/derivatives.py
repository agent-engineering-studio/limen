"""Pure numpy DEM derivatives.

All three functions take a 2D elevation array (rows = y, columns = x)
and a ``cellsize`` in metres. They return arrays of the same shape;
NaN-input → NaN-output (rasterio's nodata stays NaN end-to-end so the
zonal aggregator can ignore those pixels).

Formulas:

* **slope** — ``atan(sqrt((dz/dx)² + (dz/dy)²))`` in degrees.
* **aspect** — direction of the steepest ascent in degrees (0 = north,
  clockwise), undefined on flats (returns -1).
* **curvature** — Laplacian ``d²z/dx² + d²z/dy²`` (the simple "total"
  curvature; positive = ridge, negative = valley).

The arrays use first-order central differences via ``numpy.gradient``;
this is the Horn algorithm used by `gdaldem slope`, accurate enough
at the 10-30 m cell-size of TINITALY for landslide-susceptibility
work. We deliberately *don't* depend on scipy / richdem so this layer
stays in the core dep tree.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def _gradients(dem: Any, cellsize: float) -> tuple[Any, Any]:
    """Return ``(dz/dx, dz/dy)`` in metres-per-metre."""
    if cellsize <= 0:
        raise ValueError(f"cellsize must be > 0: {cellsize}")
    # numpy.gradient returns (axis=0=rows=y, axis=1=cols=x); convert to
    # the geographic convention (dz/dx is the horizontal change, dz/dy
    # the vertical) AND flip the y-axis sign because rasters index from
    # the top whereas geographic +y points up.
    dz_dy_pixels, dz_dx_pixels = np.gradient(dem)
    dz_dx = dz_dx_pixels / cellsize
    dz_dy = -dz_dy_pixels / cellsize  # raster row 0 is north
    return dz_dx, dz_dy


def slope_deg(dem: Any, *, cellsize: float) -> Any:
    """Slope in degrees from a DEM array."""
    dz_dx, dz_dy = _gradients(dem, cellsize)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    return np.degrees(slope_rad)


def aspect_deg(dem: Any, *, cellsize: float) -> Any:
    """Aspect (compass bearing, 0 = north, increasing clockwise)."""
    dz_dx, dz_dy = _gradients(dem, cellsize)
    # arctan2(dz/dx, dz/dy) returns the bearing of the gradient (the
    # uphill direction). Map it to compass coords: 0=N, 90=E, 180=S, 270=W.
    aspect = np.degrees(np.arctan2(dz_dx, dz_dy))
    aspect = (aspect + 360.0) % 360.0
    # Flat pixels (no gradient): mark with -1 so downstream readers can
    # ignore them rather than reporting an arbitrary direction.
    flat_mask = (np.abs(dz_dx) < 1e-9) & (np.abs(dz_dy) < 1e-9)
    aspect = np.where(flat_mask, -1.0, aspect)
    return aspect


def curvature(dem: Any, *, cellsize: float) -> Any:
    """Total Laplacian curvature (positive = ridge, negative = valley)."""
    dz_dx, dz_dy = _gradients(dem, cellsize)
    d2z_dx2 = np.gradient(dz_dx, axis=1) / cellsize
    d2z_dy2 = -np.gradient(dz_dy, axis=0) / cellsize
    return d2z_dx2 + d2z_dy2


def _is_nan_safe(value: float) -> bool:
    return not (isinstance(value, float) and math.isnan(value))


__all__ = ["aspect_deg", "curvature", "slope_deg"]
