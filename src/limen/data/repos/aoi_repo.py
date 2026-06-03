"""AOI (Area of Interest) repository.

Plain ``asyncpg`` access. No ORM. Geometries flow as Shapely objects thanks
to the PostGIS codec registered on every connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class AOI:
    id: str
    name: str
    kind: str
    geom: MultiPolygon
    bbox: Polygon
    metadata: dict[str, Any]


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    """Coerce a Polygon to MultiPolygon; leave MultiPolygon untouched."""
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise TypeError(f"AOI geometry must be (Multi)Polygon, got {type(geom).__name__}")


async def upsert_aoi(
    *,
    id: str,
    name: str,
    kind: str,
    geom: BaseGeometry,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert or update an AOI."""
    multi = _as_multipolygon(geom)
    # PostGIS gets EWKB-hex with SRID via the registered codec; we force
    # SRID=4326 here by going through the standard from_wkb on read.
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom, metadata)
            VALUES ($1, $2, $3, ST_SetSRID($4::geometry, 4326), $5::jsonb)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                kind = EXCLUDED.kind,
                geom = EXCLUDED.geom,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            id,
            name,
            kind,
            multi,
            _to_jsonb(metadata or {}),
        )


async def get_aoi(aoi_id: str) -> AOI | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, kind, geom, bbox, metadata FROM aoi WHERE id = $1",
            aoi_id,
        )
    if row is None:
        return None
    return AOI(
        id=row["id"],
        name=row["name"],
        kind=row["kind"],
        geom=row["geom"],
        bbox=row["bbox"],
        metadata=_from_jsonb(row["metadata"]),
    )


async def list_aoi_ids() -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
    return [str(r["id"]) for r in rows]


def _to_jsonb(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, default=str, separators=(",", ":"))


def _from_jsonb(value: Any) -> dict[str, Any]:
    import json

    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return dict(json.loads(value))
