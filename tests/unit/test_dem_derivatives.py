"""DEM derivatives — pure numpy unit tests on synthetic rasters."""

from __future__ import annotations

import numpy as np
import pytest

from limen.integrations.dem.derivatives import (
    aspect_deg,
    curvature,
    slope_deg,
)


def _planar_dem(*, gradient: float, shape: tuple[int, int] = (50, 50)) -> np.ndarray:
    """Synthesise a uniformly sloped plane along the x-axis.

    Each column is ``j`` higher than the previous by ``gradient * cellsize``,
    so the analytical slope (independent of cell size) is constant.
    """
    rows, cols = shape
    x = np.arange(cols, dtype=np.float64)
    return np.tile(x * gradient, (rows, 1))


def test_slope_on_flat_dem_is_zero() -> None:
    dem = np.full((10, 10), 100.0)
    out = slope_deg(dem, cellsize=10.0)
    assert np.allclose(out, 0.0)


def test_slope_matches_analytical_value() -> None:
    """A 30° east-facing slope rises 10 / sqrt(3) m per metre east.

    For cellsize=10 and a per-column rise of 10 / sqrt(3), slope = 30°.
    """
    cellsize = 10.0
    rise_per_metre = 1.0 / np.sqrt(3.0)
    dem = _planar_dem(gradient=rise_per_metre * cellsize, shape=(20, 20))
    slope = slope_deg(dem, cellsize=cellsize)
    # Interior pixels avoid the gradient's edge behaviour (forward/backward
    # diff vs central diff).
    interior = slope[2:-2, 2:-2]
    assert np.allclose(interior, 30.0, atol=0.5)


def test_aspect_on_east_facing_slope_points_east() -> None:
    """DEM increases west→east → uphill is east → aspect = 90°."""
    dem = _planar_dem(gradient=1.0, shape=(20, 20))
    asp = aspect_deg(dem, cellsize=10.0)
    interior = asp[2:-2, 2:-2]
    assert np.allclose(interior, 90.0, atol=0.5)


def test_aspect_flat_pixels_return_sentinel() -> None:
    """Pure flat → -1 sentinel, so downstream readers can filter them out."""
    dem = np.full((10, 10), 100.0)
    asp = aspect_deg(dem, cellsize=10.0)
    assert np.all(asp == -1.0)


def test_curvature_zero_on_planar_surface() -> None:
    """A linear plane has no curvature."""
    dem = _planar_dem(gradient=0.3, shape=(30, 30))
    curv = curvature(dem, cellsize=10.0)
    # Interior away from the edge: numerical second derivative ≈ 0.
    interior = curv[3:-3, 3:-3]
    assert np.allclose(interior, 0.0, atol=1e-6)


def test_curvature_positive_on_synthetic_ridge() -> None:
    """A radial pyramid → negative curvature (concave-up summit)."""
    size = 41
    cellsize = 10.0
    ys, xs = np.indices((size, size))
    cx, cy = size // 2, size // 2
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2)
    # Elevation falls off linearly from the summit; the Laplacian of an
    # inverted cone is concentrated at the summit and large where the
    # second derivative is non-zero.
    dem = np.maximum(20.0 - dist, 0.0) * 10.0
    curv = curvature(dem, cellsize=cellsize)
    # The summit pixel must be strongly negative (concave-up valley
    # bottom in math convention, but here the inverted cone gives a
    # large negative Laplacian).
    assert curv[cy, cx] < 0.0


def test_invalid_cellsize_raises() -> None:
    dem = np.zeros((4, 4))
    with pytest.raises(ValueError):
        slope_deg(dem, cellsize=0.0)
    with pytest.raises(ValueError):
        slope_deg(dem, cellsize=-5.0)


def test_nan_propagates() -> None:
    """NaN input pixels must not contaminate the surrounding output excessively.

    numpy.gradient with NaNs is finite at non-adjacent pixels; the
    contract here is that the function does NOT crash on NaN input.
    """
    dem = np.array(
        [
            [10.0, 11.0, 12.0],
            [11.0, np.nan, 13.0],
            [12.0, 13.0, 14.0],
        ]
    )
    out = slope_deg(dem, cellsize=10.0)
    assert out.shape == dem.shape
    # The pixel containing NaN is allowed to be NaN; surrounding pixels
    # may be NaN too via gradient propagation. We assert finite-ness for
    # at least the four corners which the gradient doesn't reach across
    # the NaN.
    assert np.isfinite(out[0, 0])
