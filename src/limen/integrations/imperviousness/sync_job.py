"""Fill ``cell_static_factors.imperviousness_norm`` from a CLMS raster."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

IMPERVIOUSNESS_RASTER_ENV = "LIMEN_IMPERVIOUSNESS_RASTER"

#: CLMS ships the layer as a percentage, 0-100, with 254 = "unclassifiable"
#: and 255 = nodata. Both are sentinels far outside the valid range, so a
#: plain range filter drops them without needing the raster's own nodata tag,
#: which the mosaics do not always carry.
_VALID_MAX = 100.0


def _resolve_raster_path(override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    env_value = os.environ.get(IMPERVIOUSNESS_RASTER_ENV)
    return Path(env_value) if env_value else None


async def _cell_geometries(aoi_id: str) -> dict[str, Any]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id, geom FROM grid_cells WHERE aoi_id = $1", aoi_id)
    return {str(r["id"]): r["geom"] for r in rows if r["geom"] is not None}


def cell_means(
    *, raster_path: Path, cells: dict[str, Any], src_crs_epsg: int = 4326
) -> dict[str, float]:
    """Mean sealed fraction in [0, 1] per cell, skipping cells with no pixels.

    Absent from the result rather than zero: a cell the mosaic does not cover
    is *unknown*, and writing 0 there would claim it is entirely permeable —
    which would silently suppress the urban amplification exactly where the
    data is missing.
    """
    try:
        import numpy as np
        import rasterio
        from rasterio.crs import CRS
        from rasterio.mask import mask as raster_mask
    except ImportError as exc:  # pragma: no cover — rasterio is a core dep
        raise RuntimeError("rasterio required for imperviousness zonal stats") from exc

    from limen.integrations.dem.zonal import _reproject_geom

    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"imperviousness raster not found: {path}")

    out: dict[str, float] = {}
    with rasterio.open(path) as src:
        src_crs = CRS.from_epsg(src_crs_epsg)
        for cell_id, geom in cells.items():
            projected = _reproject_geom(geom, src_crs=src_crs, dst_crs=src.crs)
            try:
                data, _ = raster_mask(src, [projected], crop=True, filled=False)
            except Exception as exc:  # pragma: no cover — rasterio errors
                log.warning(
                    "imperviousness.cell_skip",
                    cell_id=cell_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            band = data[0].astype("float32", copy=False)
            mask = np.ma.getmaskarray(band) if isinstance(band, np.ma.MaskedArray) else None
            arr = np.where(mask, np.nan, band) if mask is not None else band
            arr = np.where((arr >= 0.0) & (arr <= _VALID_MAX), arr, np.nan)
            if int(np.count_nonzero(~np.isnan(arr))) == 0:
                continue
            out[cell_id] = float(np.nanmean(arr)) / _VALID_MAX
    return out


async def sync_imperviousness_for_aois(
    *, aoi_ids: list[str], raster_path: Path | str | None = None
) -> int:
    """Write the sealed fraction for every cell of ``aoi_ids``. Returns rows written."""
    path = _resolve_raster_path(raster_path)
    if path is None:
        log.info("static_bootstrap.skip", step="imperviousness", reason="no raster configured")
        return 0
    if not path.exists():
        log.warning(
            "static_bootstrap.skip", step="imperviousness", reason="raster missing", path=str(path)
        )
        return 0

    written = 0
    for aoi_id in aoi_ids:
        cells = await _cell_geometries(aoi_id)
        if not cells:
            continue
        means = cell_means(raster_path=path, cells=cells)
        if not means:
            log.info("imperviousness.no_coverage", aoi_id=aoi_id, cells=len(cells))
            continue
        async with acquire() as conn:
            await conn.executemany(
                """
                UPDATE cell_static_factors
                   SET imperviousness_norm = $2, updated_at = now()
                 WHERE cell_id = $1
                """,
                list(means.items()),
            )
        written += len(means)
        log.info("imperviousness.aoi.done", aoi_id=aoi_id, cells_written=len(means))
    return written


__all__ = ["IMPERVIOUSNESS_RASTER_ENV", "cell_means", "sync_imperviousness_for_aois"]
