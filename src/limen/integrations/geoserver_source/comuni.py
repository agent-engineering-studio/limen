"""Reverse lookup point → comune ISTAT (GeoServer PostGIS).

The ISTAT municipal boundaries live in the GeoServer PostGIS
(``com01012023_g``, loaded by geoserver-init). Batch lookup so one
round-trip labels a whole alert list. Read-only: any failure degrades
to ``None`` per point — the UI falls back to the grid indices.
"""

from __future__ import annotations

import asyncpg

from limen.config.settings import get_settings
from limen.core.logging import get_logger

log = get_logger(__name__)


async def comuni_for_points(
    points: list[tuple[float, float]],
) -> list[str | None]:
    """Comune name per (lon, lat), aligned with the input order."""
    if not points:
        return []
    cfg = get_settings().geoserver_source
    if not cfg.db_dsn:
        return [None] * len(points)
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    try:
        conn = await asyncpg.connect(cfg.db_dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT p.i, c.comune
                FROM unnest($1::float8[], $2::float8[])
                     WITH ORDINALITY AS p(lon, lat, i)
                LEFT JOIN LATERAL (
                    SELECT comune FROM com01012023_g c
                    WHERE ST_Contains(
                        c.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))
                    LIMIT 1
                ) c ON true
                ORDER BY p.i
                """,
                lons,
                lats,
            )
        finally:
            await conn.close()
    except Exception as exc:
        log.warning(
            "integration.degraded",
            source="geoserver_source",
            op="comuni_lookup",
            error=str(exc),
        )
        return [None] * len(points)
    return [str(r["comune"]) if r["comune"] is not None else None for r in rows]


__all__ = ["comuni_for_points"]
