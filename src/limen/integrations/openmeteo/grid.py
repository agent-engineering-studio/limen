"""Rainfall sampling-node grid shared by the backtest and the live workflow.

A single AOI-centroid series cannot represent localized (convective)
triggering rain — the §2.5 test cycle measured ~13 mm at the Puglia centroid
while the truth cells received ~77 mm. Both the backtest and the operational
MeteoFetch sample precipitation on a regular node grid over the AOI bbox and
give each cell the series of its nearest node.
"""

from __future__ import annotations

import math


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


def build_snapped_nodes(
    bbox: tuple[float, float, float, float], *, spacing: float
) -> list[tuple[float, float]]:
    """A node grid snapped to a **global** lattice of multiples of ``spacing``.

    :func:`build_rain_nodes` anchors on the bbox's own corner, which is right
    for a per-run rainfall sample: the nodes exist only for that call.

    It is wrong for anything that *persists* per node. The FWI chain is keyed
    by node coordinates and takes weeks to spin up, so a grid that moves when
    an AOI boundary is redrawn -- or that differs between two overlapping
    AOIs -- would orphan every chain and silently restart the recursion.
    Snapping to a lattice makes a node's identity depend on the spacing alone,
    which is what the ``fwi_state`` invariant promises.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    start_lon = math.floor(min_lon / spacing) * spacing
    start_lat = math.floor(min_lat / spacing) * spacing
    nodes: list[tuple[float, float]] = []
    steps_lat = math.floor((max_lat - start_lat) / spacing) + 1
    steps_lon = math.floor((max_lon - start_lon) / spacing) + 1
    for i in range(max(steps_lat, 1)):
        for j in range(max(steps_lon, 1)):
            # Multiplying the step index instead of accumulating keeps the
            # coordinate exactly on the lattice: an accumulator drifts into
            # 40.99999999999999, which is a different node once it is a key.
            nodes.append((start_lon + j * spacing, start_lat + i * spacing))
    return nodes


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
