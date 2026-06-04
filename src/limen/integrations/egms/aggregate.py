"""Pure aggregation: list of scatterers → per-cell features.

Caller supplies the mapping ``cell_id → polygon`` (in EPSG:4326). The
function uses shapely's ``contains`` for the spatial join — a small N
loop is fine because the bbox is already AOI-scoped upstream.

Per-cell aggregates:
* ``insar_velocity_mmy``  — median of contained velocities (robust to
  outliers a mean would amplify);
* ``insar_accel_mmy2``    — median acceleration (None when no
  scatterer provided one);
* ``scatterer_count``     — number of contained points;
* ``period_start/end``    — earliest / latest measurement window.

A cell with no scatterers gets a row with ``count=0`` so the feature
store + ML model can still see "no signal here" deterministically.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from statistics import median

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from limen.data.repos.cell_insar_features_repo import CellInsarFeatures
from limen.integrations.egms.client import ScattererPoint


def aggregate_scatterers_to_cells(
    *,
    scatterers: list[ScattererPoint],
    cells: Mapping[str, BaseGeometry],
) -> list[CellInsarFeatures]:
    """Return one :class:`CellInsarFeatures` row per cell."""
    by_cell: dict[str, list[ScattererPoint]] = {cid: [] for cid in cells}
    for s in scatterers:
        pt = Point(s.lon, s.lat)
        for cell_id, geom in cells.items():
            if geom.contains(pt):
                by_cell[cell_id].append(s)
                break

    out: list[CellInsarFeatures] = []
    for cell_id, pts in by_cell.items():
        if not pts:
            out.append(CellInsarFeatures(cell_id=cell_id, scatterer_count=0))
            continue
        velocities = [p.velocity_mmy for p in pts]
        accels = [p.acceleration_mmy2 for p in pts if p.acceleration_mmy2 is not None]
        period_starts = [p.period_start for p in pts if p.period_start is not None]
        period_ends = [p.period_end for p in pts if p.period_end is not None]
        out.append(
            CellInsarFeatures(
                cell_id=cell_id,
                insar_velocity_mmy=float(median(velocities)),
                insar_accel_mmy2=float(median(accels)) if accels else None,
                scatterer_count=len(pts),
                period_start=_safe_min(period_starts),
                period_end=_safe_max(period_ends),
            )
        )
    return out


def _safe_min(values: list[date]) -> date | None:
    return min(values) if values else None


def _safe_max(values: list[date]) -> date | None:
    return max(values) if values else None


__all__ = ["aggregate_scatterers_to_cells"]
