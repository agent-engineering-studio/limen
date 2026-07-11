"""Matematica Web Mercator / slippy-map per comporre il basemap raster.

Formule standard OSM (tile 256px). Nessuna dipendenza esterna.
"""

from __future__ import annotations

import math

TILE = 256
_MAX_LAT = 85.05112878


def lonlat_to_pixel(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Pixel globali (0,0 in alto-sinistra) alla scala ``zoom``."""
    n = TILE * (2**zoom)
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(max(min(lat, _MAX_LAT), -_MAX_LAT))
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return (x, y)


def padded_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """bbox con margine 20% (o 0.01° minimo per bbox degeneri)."""
    minx, miny, maxx, maxy = bbox
    pad_x = (maxx - minx) * 0.2 or 0.01
    pad_y = (maxy - miny) * 0.2 or 0.01
    return (minx - pad_x, miny - pad_y, maxx + pad_x, maxy + pad_y)


def zoom_for_bbox(bbox: tuple[float, float, float, float], *, width_px: int, height_px: int) -> int:
    """Massimo zoom per cui il bbox (con margine 20%) sta nel canvas."""
    minx, miny, maxx, maxy = padded_bbox(bbox)
    for z in range(19, -1, -1):
        x0, y0 = lonlat_to_pixel(minx, maxy, z)
        x1, y1 = lonlat_to_pixel(maxx, miny, z)
        if (x1 - x0) <= width_px and (y1 - y0) <= height_px:
            return z
    return 0


def tile_range_for_bbox(
    bbox: tuple[float, float, float, float], zoom: int
) -> tuple[int, int, int, int]:
    """Indici tile (x0,y0,x1,y1) che coprono il bbox allo zoom dato."""
    minx, miny, maxx, maxy = bbox
    px0, py0 = lonlat_to_pixel(minx, maxy, zoom)
    px1, py1 = lonlat_to_pixel(maxx, miny, zoom)
    return (
        int(px0 // TILE),
        int(py0 // TILE),
        int(px1 // TILE),
        int(py1 // TILE),
    )
