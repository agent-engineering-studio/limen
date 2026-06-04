"""Geological sync job — read shapefile(s), fill cell_static_factors.

Two env vars wire the shapefiles:

* ``LIMEN_GEOLOGICAL_SHAPEFILE`` — polygon shapefile carrying the
  lithology label in a configurable attribute column
  (``LIMEN_GEOLOGICAL_FIELD``, default ``litologia``).
* ``LIMEN_FAULTS_SHAPEFILE`` — optional; line shapefile with the fault
  geometries. Unset → ``dist_faults_m`` stays NULL.

Both shapefiles are read once, reprojected to EPSG:4326, then the
per-cell aggregator runs over the AOI grid.
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
from limen.integrations.geological.zonal import (
    LithologyPolygon,
    compute_geological_stats,
)

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


LITHO_SHAPEFILE_ENV = "LIMEN_GEOLOGICAL_SHAPEFILE"
LITHO_FIELD_ENV = "LIMEN_GEOLOGICAL_FIELD"
FAULTS_SHAPEFILE_ENV = "LIMEN_FAULTS_SHAPEFILE"


def _resolve_path(env_var: str, override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    value = os.environ.get(env_var)
    return Path(value) if value else None


def _read_polygons(shapefile_path: Path, *, field: str) -> list[LithologyPolygon]:
    import geopandas as gpd

    gdf = gpd.read_file(shapefile_path)
    if gdf.crs is None:
        raise ValueError(f"{shapefile_path}: shapefile has no CRS")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    if field not in gdf.columns:
        # Fall back to the first text-typed column; better than crashing.
        text_cols = [c for c in gdf.columns if gdf[c].dtype == object and c != "geometry"]
        if not text_cols:
            raise ValueError(f"{shapefile_path}: column {field!r} not found and no text fallback")
        field = text_cols[0]
        _log.warning(
            "geological.litho.field_fallback",
            requested=field,
            fallback=field,
            available=list(gdf.columns),
        )
    out: list[LithologyPolygon] = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        label = row.get(field)
        if label is None:
            continue
        out.append(LithologyPolygon(geom=geom, label=str(label)))
    return out


def _read_faults(shapefile_path: Path) -> list[object]:
    import geopandas as gpd

    gdf = gpd.read_file(shapefile_path)
    if gdf.crs is None:
        raise ValueError(f"{shapefile_path}: shapefile has no CRS")
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    return [g for g in gdf.geometry if g is not None and not g.is_empty]


async def _load_cell_geometries(aoi_id: str) -> dict[str, object]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, geom FROM grid_cells WHERE aoi_id = $1",
            aoi_id,
        )
    return {str(r["id"]): r["geom"] for r in rows if r["geom"] is not None}


async def sync_geological_for_aois(
    *,
    aoi_ids: list[str],
    lithology_shapefile: Path | str | None = None,
    faults_shapefile: Path | str | None = None,
    field: str | None = None,
) -> int:
    """Compute lithology + fault distance per cell; upsert into the operational DB."""
    litho_path = _resolve_path(LITHO_SHAPEFILE_ENV, lithology_shapefile)
    if litho_path is None:
        _log.info(
            "geological.sync.skip_no_shapefile",
            hint=f"set {LITHO_SHAPEFILE_ENV} to enable this step",
        )
        return 0
    if not litho_path.exists():
        _log.warning("geological.sync.shapefile_missing", path=str(litho_path))
        return 0
    litho_field = field or os.environ.get(LITHO_FIELD_ENV, "litologia")

    try:
        polygons = _read_polygons(litho_path, field=litho_field)
    except Exception as exc:
        _log.warning(
            "geological.sync.read_failed",
            path=str(litho_path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0

    faults_path = _resolve_path(FAULTS_SHAPEFILE_ENV, faults_shapefile)
    faults: list[object] = []
    if faults_path is not None and faults_path.exists():
        try:
            faults = _read_faults(faults_path)
        except Exception as exc:
            _log.warning(
                "geological.sync.faults_read_failed",
                path=str(faults_path),
                error=str(exc),
            )

    total = 0
    for aoi_id in aoi_ids:
        cells = await _load_cell_geometries(aoi_id)
        if not cells:
            continue
        stats = compute_geological_stats(
            cells=cells,
            lithology_polygons=polygons,
            faults=faults,
        )
        rows = [
            CellStaticFactors(
                cell_id=s.cell_id,
                lithology=s.lithology,
                litho_weight=s.litho_weight,
                dist_faults_m=s.dist_faults_m,
            )
            for s in stats
            if s.lithology is not None or s.dist_faults_m is not None
        ]
        if rows:
            written = await upsert_many(rows)
            total += written
            _log.info(
                "geological.sync.aoi_done",
                aoi_id=aoi_id,
                rows_written=written,
                with_faults=sum(1 for s in stats if s.dist_faults_m is not None),
            )
    return total


__all__ = [
    "FAULTS_SHAPEFILE_ENV",
    "LITHO_FIELD_ENV",
    "LITHO_SHAPEFILE_ENV",
    "sync_geological_for_aois",
]
