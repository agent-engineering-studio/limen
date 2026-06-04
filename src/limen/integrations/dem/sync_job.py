"""DEM sync job — fill cell_static_factors from a TINITALY-style raster.

Run from ``limen bootstrap-static`` (already wired) when the env var
``LIMEN_DEM_RASTER`` is set. With the variable unset, the orchestrator
logs ``static_bootstrap.skip`` for the DEM step and moves on — same
graceful-degradation contract as the rest of the bootstrap.

This is a low-cadence job (DEM mosaics refresh maybe yearly). It is
NEVER part of the hourly critical path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos.cell_static_factors_repo import (
    CellStaticFactors,
    upsert_many,
)
from limen.integrations.dem.zonal import compute_cell_stats

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


DEM_RASTER_ENV = "LIMEN_DEM_RASTER"


def _resolve_raster_path(override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    env_value = os.environ.get(DEM_RASTER_ENV)
    return Path(env_value) if env_value else None


async def _load_cell_geometries(aoi_id: str) -> dict[str, Any]:
    """Return ``{cell_id: shapely.Geometry}`` for one AOI."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, geom FROM grid_cells WHERE aoi_id = $1",
            aoi_id,
        )
    out: dict[str, Any] = {}
    for r in rows:
        geom = r["geom"]
        if geom is None:
            continue
        out[str(r["id"])] = geom
    return out


async def sync_dem_for_aois(
    *,
    aoi_ids: list[str],
    raster_path: Path | str | None = None,
) -> int:
    """Compute + upsert DEM stats for every cell in every listed AOI.

    Returns the total number of cells written. With no raster path
    configured the job logs and returns 0 (the rest of the bootstrap
    keeps going).
    """
    resolved = _resolve_raster_path(raster_path)
    if resolved is None:
        _log.info(
            "dem.sync.skip_no_raster",
            hint=f"set {DEM_RASTER_ENV} to a GeoTIFF path to enable this step",
        )
        return 0
    if not resolved.exists():
        _log.warning("dem.sync.raster_missing", path=str(resolved))
        return 0

    total_written = 0
    for aoi_id in aoi_ids:
        cells = await _load_cell_geometries(aoi_id)
        if not cells:
            _log.info("dem.sync.no_cells", aoi_id=aoi_id)
            continue
        stats = compute_cell_stats(raster_path=resolved, cells=cells)
        rows = [
            CellStaticFactors(
                cell_id=s.cell_id,
                elevation_m=s.elevation_m,
                slope_deg=s.slope_deg,
                aspect_deg=s.aspect_deg,
                curvature=s.curvature,
            )
            for s in stats
            if s.pixel_count > 0
        ]
        if rows:
            written = await upsert_many(rows)
            total_written += written
            _log.info(
                "dem.sync.aoi_done",
                aoi_id=aoi_id,
                cells_with_data=len(rows),
                rows_written=written,
            )
        else:
            _log.warning(
                "dem.sync.aoi_no_pixels",
                aoi_id=aoi_id,
                cells_in=len(cells),
                hint="raster does not cover this AOI",
            )
    return total_written


__all__ = ["DEM_RASTER_ENV", "sync_dem_for_aois"]
