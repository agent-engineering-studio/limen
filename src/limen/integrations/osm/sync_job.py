"""OSM sync job — load pre-extracted road/rail vectors into PostGIS.

The network is national, so this runs once per bootstrap (not per AOI);
`limen bootstrap-static` calls it before the per-AOI distance pass.

Two env vars wire the files (any OGR-readable vector format):

* ``LIMEN_OSM_ROADS`` — main road network, e.g. extracted from the
  Geofabrik Italy PBF with::

      ogr2ogr -f GPKG osm_roads.gpkg italy-latest.osm.pbf lines \\
        -where "highway IN ('motorway','trunk','primary','secondary')"

* ``LIMEN_OSM_RAILWAYS`` — railway lines::

      ogr2ogr -f GPKG osm_rails.gpkg italy-latest.osm.pbf lines \\
        -where "railway = 'rail'"

Data © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire

_log: structlog.stdlib.BoundLogger = get_logger(__name__)

OSM_ROADS_ENV = "LIMEN_OSM_ROADS"
OSM_RAILWAYS_ENV = "LIMEN_OSM_RAILWAYS"

_INSERT_SQL = "INSERT INTO osm_infrastructure (kind, class, geom) VALUES ($1, $2, $3)"


def _resolve_path(env_var: str, override: Path | str | None) -> Path | None:
    if override is not None:
        return Path(override)
    value = os.environ.get(env_var)
    return Path(value) if value else None


def _read_lines(path: Path, *, class_field: str | None) -> list[tuple[str | None, BaseGeometry]]:
    """Read a vector file and return ``(class, LineString)`` pairs.

    MultiLineStrings are exploded so the table column stays a plain
    LineString and the KNN distance sees each segment individually.
    """
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")
    out: list[tuple[str | None, BaseGeometry]] = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        cls = row.get(class_field) if class_field and class_field in gdf.columns else None
        parts = geom.geoms if geom.geom_type == "MultiLineString" else [geom]
        for part in parts:
            if part.geom_type == "LineString":
                out.append((str(cls) if cls is not None else None, part))
    return out


async def _sync_kind(kind: str, path: Path, *, class_field: str | None) -> int:
    try:
        lines = _read_lines(path, class_field=class_field)
    except Exception as exc:
        _log.warning(
            "osm.sync.read_failed",
            kind=kind,
            path=str(path),
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0
    if not lines:
        _log.warning("osm.sync.empty", kind=kind, path=str(path))
        return 0
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM osm_infrastructure WHERE kind = $1", kind)
        await conn.executemany(_INSERT_SQL, [(kind, cls, geom) for cls, geom in lines])
    _log.info("osm.sync.kind_done", kind=kind, features=len(lines), path=str(path))
    return len(lines)


async def sync_osm_infrastructure(
    *,
    roads_path: Path | str | None = None,
    railways_path: Path | str | None = None,
) -> int:
    """Replace the ``osm_infrastructure`` table content per kind.

    Each kind is independent and opt-in; with both env vars unset this
    is a clean no-op + log line, never a raise.
    """
    total = 0
    for kind, env_var, override, class_field in (
        ("road", OSM_ROADS_ENV, roads_path, "highway"),
        ("rail", OSM_RAILWAYS_ENV, railways_path, None),
    ):
        path = _resolve_path(env_var, override)
        if path is None:
            _log.info(f"osm.sync.skip_no_{kind}s", hint=f"set {env_var} to enable this step")
            continue
        if not path.exists():
            _log.warning("osm.sync.file_missing", kind=kind, path=str(path))
            continue
        total += await _sync_kind(kind, path, class_field=class_field)
    return total


__all__ = ["OSM_RAILWAYS_ENV", "OSM_ROADS_ENV", "sync_osm_infrastructure"]
