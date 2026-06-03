"""Grid repository — generate and store a 1 km² discretisation grid.

The grid is generated in a metric CRS (EPSG:3035 ETRS89-extended / LAEA
Europe, well suited for the Italian peninsula) so that 1 km is actually
1 km, then reprojected back to EPSG:4326 for storage.

Cell IDs are deterministic: ``<aoi_id>|<row_idx>|<col_idx>``. Re-running the
generation is therefore idempotent (``ON CONFLICT DO NOTHING``).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import geopandas as gpd
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos.aoi_repo import get_aoi

log = get_logger(__name__)

# 1 km² nominal cell size, defined in the metric CRS used for generation.
DEFAULT_CELL_SIZE_M = 1_000.0
METRIC_CRS = "EPSG:3035"
GEO_CRS = "EPSG:4326"


@dataclass(frozen=True, slots=True)
class GridCell:
    id: str
    aoi_id: str
    row_idx: int
    col_idx: int
    geom: Polygon
    area_km2: float


def _generate_cells(
    aoi_id: str,
    aoi_geom: BaseGeometry,
    cell_size_m: float,
) -> list[GridCell]:
    """Generate cells in metric CRS and return them in EPSG:4326."""
    gdf_geo = gpd.GeoSeries([aoi_geom], crs=GEO_CRS)
    gdf_metric = gdf_geo.to_crs(METRIC_CRS)
    metric_geom = gdf_metric.iloc[0]

    minx, miny, maxx, maxy = metric_geom.bounds
    n_rows = ceil((maxy - miny) / cell_size_m)
    n_cols = ceil((maxx - minx) / cell_size_m)

    candidates: list[Polygon] = []
    indices: list[tuple[int, int]] = []
    for r in range(n_rows):
        for c in range(n_cols):
            x0 = minx + c * cell_size_m
            y0 = miny + r * cell_size_m
            candidates.append(box(x0, y0, x0 + cell_size_m, y0 + cell_size_m))
            indices.append((r, c))

    if not candidates:
        return []

    cells_metric = gpd.GeoSeries(candidates, crs=METRIC_CRS)
    mask = cells_metric.intersects(metric_geom)
    keep_metric = cells_metric[mask]
    keep_indices = [indices[i] for i, m in enumerate(mask.tolist()) if m]

    keep_geo = keep_metric.to_crs(GEO_CRS)

    out: list[GridCell] = []
    cell_area_km2 = (cell_size_m * cell_size_m) / 1_000_000.0
    for (r, c), geom in zip(keep_indices, keep_geo.tolist(), strict=True):
        out.append(
            GridCell(
                id=f"{aoi_id}|{r}|{c}",
                aoi_id=aoi_id,
                row_idx=r,
                col_idx=c,
                geom=geom,
                area_km2=cell_area_km2,
            )
        )
    return out


async def generate_and_store_grid(
    aoi_id: str,
    *,
    cell_size_m: float = DEFAULT_CELL_SIZE_M,
) -> int:
    """Generate a grid for ``aoi_id`` and upsert cells.

    Returns the number of cells inserted (excluding duplicates).
    """
    aoi = await get_aoi(aoi_id)
    if aoi is None:
        raise ValueError(f"AOI not found: {aoi_id!r}")

    cells = _generate_cells(aoi.id, aoi.geom, cell_size_m)
    log.info(
        "grid.generate",
        aoi_id=aoi_id,
        candidates=len(cells),
        cell_size_m=cell_size_m,
    )

    inserted = 0
    async with acquire() as conn, conn.transaction():
        for cell in cells:
            result = await conn.execute(
                """
                INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
                VALUES ($1, $2, $3, $4, ST_SetSRID($5::geometry, 4326), $6)
                ON CONFLICT (id) DO NOTHING
                """,
                cell.id,
                cell.aoi_id,
                cell.row_idx,
                cell.col_idx,
                cell.geom,
                cell.area_km2,
            )
            if result.startswith("INSERT") and not result.endswith(" 0"):
                inserted += 1

    log.info("grid.stored", aoi_id=aoi_id, inserted=inserted, total=len(cells))
    return inserted


async def count_grid_cells(aoi_id: str) -> int:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*)::bigint AS n FROM grid_cells WHERE aoi_id = $1", aoi_id
        )
    return int(row["n"]) if row else 0


__all__ = [
    "DEFAULT_CELL_SIZE_M",
    "GridCell",
    "count_grid_cells",
    "generate_and_store_grid",
]
