"""Per-cell aggregation of geological polygons + fault lines.

The function takes two shapely datasets (already loaded as GeoDataFrames
or as bare ``(geometry, lithology_label)`` tuples) and computes:

* ``lithology`` — the label whose intersection area with the cell is
  largest. Ties resolve in lexical order.
* ``litho_weight`` — the susceptibility weight from
  :func:`normalise_litho`.
* ``dist_faults_m`` — geodesic distance from the cell centroid to the
  nearest fault line, capped at ``DISTANCE_CAP_M``.

All inputs are assumed to be in EPSG:4326; callers can reproject
upstream if their source is in UTM / Lambert. The function is pure
shapely — no rasterio dep needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from limen.core.logging import get_logger
from limen.integrations.geological.litho_weights import normalise_litho

_log: structlog.stdlib.BoundLogger = get_logger(__name__)

DISTANCE_CAP_M = 50_000.0
"""Cap the fault-distance reporting at 50 km — beyond this, the cell is
"far from any mapped fault" for landslide-engine purposes."""


@dataclass(frozen=True, slots=True)
class CellGeologicalStats:
    cell_id: str
    lithology: str | None
    litho_weight: float | None
    dist_faults_m: float | None


@dataclass(frozen=True, slots=True)
class LithologyPolygon:
    geom: BaseGeometry
    label: str


def _haversine_m(lon_a: float, lat_a: float, lon_b: float, lat_b: float) -> float:
    """Geodesic distance on the WGS84 sphere — accurate enough for "is it < 50 km"."""
    earth_r = 6_371_008.8  # metres
    lat_a_r = math.radians(lat_a)
    lat_b_r = math.radians(lat_b)
    dlat = math.radians(lat_b - lat_a)
    dlon = math.radians(lon_b - lon_a)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat_a_r) * math.cos(lat_b_r) * math.sin(dlon / 2) ** 2
    return float(2 * earth_r * math.asin(math.sqrt(h)))


def _dominant_lithology(
    cell_geom: BaseGeometry, tree: STRtree, polygons: list[LithologyPolygon]
) -> tuple[str | None, float | None]:
    """Return ``(label, weight)`` for the lithology covering the most area."""
    indices = tree.query(cell_geom)
    if len(indices) == 0:
        return None, None
    best_label: str | None = None
    best_weight: float | None = None
    best_area = 0.0
    for idx in indices:
        poly = polygons[int(idx)]
        intersection = cell_geom.intersection(poly.geom)
        area = float(intersection.area)
        if area <= 0:
            continue
        if area > best_area or (
            area == best_area and best_label is not None and poly.label < best_label
        ):
            best_area = area
            label, weight = normalise_litho(poly.label)
            best_label = poly.label
            best_weight = weight
            _ = label  # canonical key used inside normalise_litho
    return best_label, best_weight


def _nearest_fault_distance(
    cell_geom: BaseGeometry, fault_tree: STRtree, faults: list[BaseGeometry]
) -> float | None:
    """Distance (m) from the cell centroid to the nearest fault, capped."""
    if not faults:
        return None
    centroid = cell_geom.centroid
    # Use the spatial index to short-circuit the search; the bbox of a
    # reasonable AOI is much smaller than the global cap, so we widen
    # the search box conservatively.
    search_buffer = centroid.buffer(0.5)  # ~50 km at the equator, more at lower lat
    indices = fault_tree.query(search_buffer)
    candidates = [faults[int(i)] for i in indices]
    if not candidates:
        return DISTANCE_CAP_M
    best = DISTANCE_CAP_M
    for fault in candidates:
        nearest = fault.interpolate(fault.project(centroid))
        d = _haversine_m(centroid.x, centroid.y, nearest.x, nearest.y)
        if d < best:
            best = d
    return float(best)


def compute_geological_stats(
    *,
    cells: dict[str, BaseGeometry],
    lithology_polygons: list[LithologyPolygon],
    faults: list[BaseGeometry] | None = None,
) -> list[CellGeologicalStats]:
    """Aggregate the geological dataset over every cell."""
    polygons = [p for p in lithology_polygons if not p.geom.is_empty]
    litho_tree = STRtree([p.geom for p in polygons]) if polygons else None
    faults_clean = [f for f in (faults or []) if not f.is_empty]
    fault_tree = STRtree(faults_clean) if faults_clean else None

    out: list[CellGeologicalStats] = []
    for cell_id, cell_geom in cells.items():
        litho_label, litho_weight = (
            _dominant_lithology(cell_geom, litho_tree, polygons)
            if litho_tree is not None
            else (None, None)
        )
        dist = (
            _nearest_fault_distance(cell_geom, fault_tree, faults_clean)
            if fault_tree is not None
            else None
        )
        out.append(
            CellGeologicalStats(
                cell_id=cell_id,
                lithology=litho_label,
                litho_weight=litho_weight,
                dist_faults_m=dist,
            )
        )
    _log.info(
        "geological.zonal.done",
        cells=len(cells),
        with_lithology=sum(1 for s in out if s.lithology is not None),
        with_fault_distance=sum(1 for s in out if s.dist_faults_m is not None),
    )
    return out


__all__ = [
    "DISTANCE_CAP_M",
    "CellGeologicalStats",
    "LithologyPolygon",
    "compute_geological_stats",
]
