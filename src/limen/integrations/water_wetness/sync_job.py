"""Fill ``cell_static_factors.water_wetness_temp`` from the HRL WaterWetness raster."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

WATER_WETNESS_RASTER_ENV = "LIMEN_WATER_WETNESS_RASTER"

#: Classes that count as observed ground: 0 dry, 1 permanent water, 2
#: temporary water, 3 permanent wet, 4 temporary wet. Sea (253),
#: unclassifiable (254), outside (255) and anything else are unknown.
_CLASSI_VALIDE_MAX = 4
_TEMPORANEE = (2, 4)

#: Below this many classified pixels a cell stays NULL. At 50 m a 1 km cell
#: holds ~400 pixels: under a quarter of it classified (a coastal sliver, a
#: border cell) the share would rest on a handful of pixels.
MIN_PIXELS = 100


def _resolve_raster_path(override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    env_value = os.environ.get(WATER_WETNESS_RASTER_ENV)
    return Path(env_value) if env_value else None


async def _cell_geometries(aoi_id: str) -> dict[str, Any]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id, geom FROM grid_cells WHERE aoi_id = $1", aoi_id)
    return {str(r["id"]): r["geom"] for r in rows if r["geom"] is not None}


def cell_shares(
    *,
    raster_path: Path,
    cells: dict[str, Any],
    src_crs_epsg: int = 4326,
    min_pixels: int = MIN_PIXELS,
) -> dict[str, float]:
    """Temporary water + wet share in [0, 1] per cell, skipping thin cells.

    Absent from the result rather than zero: zero claims water was never seen
    there, which a cell the raster does not cover cannot say.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.crs import CRS
        from rasterio.mask import mask as raster_mask
    except ImportError as exc:  # pragma: no cover — rasterio is a core dep
        raise RuntimeError("rasterio required for water-wetness zonal stats") from exc

    from limen.integrations.dem.zonal import geom_reprojector

    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"water-wetness raster not found: {path}")

    out: dict[str, float] = {}
    with rasterio.open(path) as src:
        reproject = geom_reprojector(src_crs=CRS.from_epsg(src_crs_epsg), dst_crs=src.crs)
        for cell_id, geom in cells.items():
            try:
                data, _ = raster_mask(src, [reproject(geom)], crop=True, filled=False)
            except Exception as exc:  # pragma: no cover — rasterio errors
                log.warning(
                    "water_wetness.cell_skip",
                    cell_id=cell_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            band = data[0]
            dentro = ~np.ma.getmaskarray(band)
            valori = np.asarray(band)[dentro]
            validi = valori[valori <= _CLASSI_VALIDE_MAX]
            if validi.size < min_pixels:
                continue
            out[cell_id] = float(np.isin(validi, _TEMPORANEE).sum()) / float(validi.size)
    return out


async def sync_water_wetness_for_aois(
    *, aoi_ids: list[str], raster_path: Path | str | None = None
) -> int:
    """Write the temporary share for every cell of ``aoi_ids``. Returns rows written."""
    path = _resolve_raster_path(raster_path)
    if path is None:
        log.info("static_bootstrap.skip", step="water_wetness", reason="no raster configured")
        return 0
    if not path.exists():
        log.warning(
            "static_bootstrap.skip", step="water_wetness", reason="raster missing", path=str(path)
        )
        return 0

    written = 0
    for aoi_id in aoi_ids:
        cells = await _cell_geometries(aoi_id)
        if not cells:
            continue
        shares = cell_shares(raster_path=path, cells=cells)
        if not shares:
            log.info("water_wetness.no_coverage", aoi_id=aoi_id, cells=len(cells))
            continue
        async with acquire() as conn:
            await conn.executemany(
                """
                UPDATE cell_static_factors
                   SET water_wetness_temp = $2, updated_at = now()
                 WHERE cell_id = $1
                """,
                list(shares.items()),
            )
        written += len(shares)
        log.info("water_wetness.aoi.done", aoi_id=aoi_id, cells_written=len(shares))
    return written


__all__ = ["MIN_PIXELS", "WATER_WETNESS_RASTER_ENV", "cell_shares", "sync_water_wetness_for_aois"]
