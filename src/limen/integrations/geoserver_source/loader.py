"""Load ISPRA static data from the GeoServer PostGIS into operational tables.

The GeoServer stack (mcp-geo-server) publishes the ISPRA open data as
per-region PostGIS tables. This loader reads the landslide inventory
families and the PAI hazard mosaic for one AOI and upserts them into the
operational ``iffi_landslides`` / ``pai_hazard`` tables, so the existing
``bootstrap-static`` per-cell aggregation runs unchanged.
"""

from __future__ import annotations

import re

import asyncpg

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, register_postgis
from limen.data.repos.iffi_repo import IFFILandslide
from limen.data.repos.iffi_repo import upsert_many as iffi_upsert
from limen.data.repos.pai_repo import PAIHazard
from limen.data.repos.pai_repo import upsert_many as pai_upsert

log = get_logger(__name__)

# Landslide-inventory families published per region as
# ``<family>_<region>_opendata`` (polygons, lines, points).
_IFFI_FAMILIES = ("frane_poly", "frane_line", "frane_piff", "aree_poly", "dgpv_poly")

# National PAI landslide-hazard mosaic (single table, ~900k polygons).
_PAI_TABLE = "mosaicatura_ispra_2020_2021_aree_pericolosita_frana_pai"
_PAI_ATTR = "per_fr_ita"

# Preferred stable id columns; fall back to a geometry hash when absent.
_ID_COL_PREFERENCE = ("id_frana", "fid", "ogc_fid", "gid", "objectid")

# PAI class token embedded in the free-text ``per_fr_ita`` label
# (e.g. "Aree di Attenzione AA", "Elevata P3").
_PAI_TOKEN_RE = re.compile(r"\b(AA|P[1-4])\b", re.IGNORECASE)


def _region_token(aoi_id: str) -> str:
    """Map an AOI id (e.g. ``it-puglia``) to the region table suffix."""
    token = aoi_id.strip().lower().replace("-", "_")
    for prefix in ("it_", "ita_"):
        if token.startswith(prefix):
            return token[len(prefix) :]
    return token


def _pai_class_token(value: str | None) -> str | None:
    if not value:
        return None
    match = _PAI_TOKEN_RE.search(value)
    return match.group(1).upper() if match else None


async def _table_columns(conn: asyncpg.Connection, schema: str, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        """,
        schema,
        table,
    )
    return {r["column_name"] for r in rows}


async def _aoi_bbox(aoi_id: str) -> tuple[float, float, float, float] | None:
    """Bounding box of the AOI's grid cells, for the PAI spatial filter."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(e) AS minx, ST_YMin(e) AS miny,
                   ST_XMax(e) AS maxx, ST_YMax(e) AS maxy
            FROM (SELECT ST_Extent(geom) AS e FROM grid_cells WHERE aoi_id = $1) s
            """,
            aoi_id,
        )
    if row is None or row["minx"] is None:
        return None
    return (float(row["minx"]), float(row["miny"]), float(row["maxx"]), float(row["maxy"]))


async def _load_iffi(conn: asyncpg.Connection, schema: str, region: str) -> list[IFFILandslide]:
    items: list[IFFILandslide] = []
    for family in _IFFI_FAMILIES:
        table = f"{family}_{region}_opendata"
        cols = await _table_columns(conn, schema, table)
        if "geom" not in cols:
            continue
        id_col = next((c for c in _ID_COL_PREFERENCE if c in cols), None)
        id_expr = f'"{id_col}"::text' if id_col else 'md5(ST_AsEWKB("geom"))'
        move_col = "nome_tipo" if "nome_tipo" in cols else None
        move_expr = f'"{move_col}"::text' if move_col else "NULL::text"
        rows = await conn.fetch(
            f'SELECT {id_expr} AS rid, {move_expr} AS movement, "geom" AS geom '
            f'FROM "{schema}"."{table}"'
        )
        for r in rows:
            geom = r["geom"]
            if geom is None:
                continue
            items.append(
                IFFILandslide(
                    id=f"{table}:{r['rid']}",
                    movement_type=r["movement"],
                    state=None,
                    velocity_class=None,
                    occurrence_date=None,
                    geom=geom,
                    attributes={"source": "geoserver", "family": family, "region": region},
                )
            )
    return items


async def _load_pai(
    conn: asyncpg.Connection, schema: str, bbox: tuple[float, float, float, float]
) -> list[PAIHazard]:
    cols = await _table_columns(conn, schema, _PAI_TABLE)
    if "geom" not in cols or _PAI_ATTR not in cols:
        return []
    id_col = next((c for c in _ID_COL_PREFERENCE if c in cols), None)
    id_expr = f'"{id_col}"::text' if id_col else 'md5(ST_AsEWKB("geom"))'
    rows = await conn.fetch(
        f'SELECT {id_expr} AS rid, "{_PAI_ATTR}"::text AS cls, "geom" AS geom '
        f'FROM "{schema}"."{_PAI_TABLE}" '
        "WHERE ST_Intersects(geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))",
        bbox[0],
        bbox[1],
        bbox[2],
        bbox[3],
    )
    items: list[PAIHazard] = []
    for r in rows:
        token = _pai_class_token(r["cls"])
        geom = r["geom"]
        if token is None or geom is None:
            continue
        items.append(
            PAIHazard(
                id=f"pai:{r['rid']}",
                hazard_class=token,
                authority=None,
                geom=geom,
                attributes={"source": "geoserver", "per_fr_ita": r["cls"]},
            )
        )
    return items


async def sync_geoserver_source_for_aoi(aoi_id: str) -> dict[str, int]:
    """Sync IFFI + PAI for ``aoi_id`` from GeoServer PostGIS.

    Returns per-dataset row counts. No-op (all zeros) when the source DSN is
    unset; degrades to zeros + an ``integration.degraded`` log when the
    GeoServer PostGIS is unreachable (read side never raises).
    """
    cfg = get_settings().geoserver_source
    if not cfg.db_dsn:
        log.info("geoserver_source.skip_no_dsn", aoi_id=aoi_id)
        return {"iffi": 0, "pai": 0}

    region = _region_token(aoi_id)
    bbox = await _aoi_bbox(aoi_id)

    try:
        conn = await asyncpg.connect(cfg.db_dsn)
    except (OSError, asyncpg.PostgresError) as exc:
        log.warning("integration.degraded", source="geoserver_source", op="connect", error=str(exc))
        return {"iffi": 0, "pai": 0}

    try:
        await register_postgis(conn)
        iffi_items = await _load_iffi(conn, cfg.schema_name, region)
        pai_items = await _load_pai(conn, cfg.schema_name, bbox) if bbox else []
    except (OSError, asyncpg.PostgresError) as exc:
        log.warning("integration.degraded", source="geoserver_source", op="read", error=str(exc))
        return {"iffi": 0, "pai": 0}
    finally:
        await conn.close()

    iffi_n = await iffi_upsert(iffi_items)
    pai_n = await pai_upsert(pai_items)
    log.info(
        "geoserver_source.synced",
        aoi_id=aoi_id,
        region=region,
        iffi=iffi_n,
        pai=pai_n,
    )
    return {"iffi": iffi_n, "pai": pai_n}
