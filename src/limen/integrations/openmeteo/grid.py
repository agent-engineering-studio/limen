"""Rainfall sampling-node grid shared by the backtest and the live workflow.

A single AOI-centroid series cannot represent localized (convective)
triggering rain — the §2.5 test cycle measured ~13 mm at the Puglia centroid
while the truth cells received ~77 mm. Both the backtest and the operational
MeteoFetch sample precipitation on a regular node grid over the AOI bbox and
give each cell the series of its nearest node.
"""

from __future__ import annotations


def build_rain_nodes(
    bbox: tuple[float, float, float, float], *, spacing: float
) -> list[tuple[float, float]]:
    """A regular ``(lon, lat)`` grid over ``bbox`` at ``spacing`` degrees."""
    min_lon, min_lat, max_lon, max_lat = bbox
    nodes: list[tuple[float, float]] = []
    lat = min_lat
    while lat <= max_lat + 1e-9:
        lon = min_lon
        while lon <= max_lon + 1e-9:
            nodes.append((lon, lat))
            lon += spacing
        lat += spacing
    return nodes or [((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0)]


def nearest_node(lon: float, lat: float, nodes: list[tuple[float, float]]) -> int:
    """Index of the node closest to ``(lon, lat)`` (planar — fine at ≤0.25°)."""
    best_i = 0
    best_d = float("inf")
    for i, (nlon, nlat) in enumerate(nodes):
        d = (lon - nlon) ** 2 + (lat - nlat) ** 2
        if d < best_d:
            best_d = d
            best_i = i
    return best_i
