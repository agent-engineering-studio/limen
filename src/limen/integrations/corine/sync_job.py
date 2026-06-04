"""CORINE sync job — fill cell_static_factors.landuse_code.

Runs from ``limen bootstrap-static`` when ``LIMEN_CORINE_RASTER`` is
set. With the env var unset the step is a clean no-op + structured
log.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos.cell_static_factors_repo import (
    CellStaticFactors,
    upsert_many,
)
from limen.integrations.corine.zonal import compute_landuse_stats

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


CORINE_RASTER_ENV = "LIMEN_CORINE_RASTER"


def _resolve_raster_path(override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    env_value = os.environ.get(CORINE_RASTER_ENV)
    return Path(env_value) if env_value else None


async def _load_cell_geometries(aoi_id: str) -> dict[str, object]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, geom FROM grid_cells WHERE aoi_id = $1",
            aoi_id,
        )
    return {str(r["id"]): r["geom"] for r in rows if r["geom"] is not None}


async def sync_corine_for_aois(
    *,
    aoi_ids: list[str],
    raster_path: Path | str | None = None,
) -> int:
    resolved = _resolve_raster_path(raster_path)
    if resolved is None:
        _log.info(
            "corine.sync.skip_no_raster",
            hint=f"set {CORINE_RASTER_ENV} to a CORINE GeoTIFF to enable this step",
        )
        return 0
    if not resolved.exists():
        _log.warning("corine.sync.raster_missing", path=str(resolved))
        return 0

    total = 0
    for aoi_id in aoi_ids:
        cells = await _load_cell_geometries(aoi_id)
        if not cells:
            continue
        stats = compute_landuse_stats(raster_path=resolved, cells=cells)
        rows = [
            CellStaticFactors(cell_id=s.cell_id, landuse_code=s.landuse_code)
            for s in stats
            if s.pixel_count > 0 and s.landuse_code is not None
        ]
        if rows:
            written = await upsert_many(rows)
            total += written
            _log.info(
                "corine.sync.aoi_done",
                aoi_id=aoi_id,
                rows_written=written,
            )
    return total


__all__ = ["CORINE_RASTER_ENV", "sync_corine_for_aois"]
