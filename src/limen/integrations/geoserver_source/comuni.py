"""Reverse lookup point → comune ISTAT.

The ISTAT municipal boundaries (``com01012023_g``) live in Limen's database,
schema ``sorgenti`` (``limen carica-vettori``, #426), or in an external
PostGIS when ``GEOSERVER_SOURCE__DB_DSN`` points at one. Batch lookup so one
round-trip labels a whole alert list. Read-only: any failure degrades
to ``None`` per point — the UI falls back to the grid indices.
"""

from __future__ import annotations

import asyncpg

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


async def comuni_for_points(
    points: list[tuple[float, float]],
) -> list[str | None]:
    """Comune name per (lon, lat), aligned with the input order."""
    if not points:
        return []
    settings = get_settings()
    dsn, schema = settings.geoserver_source.sorgente(settings.db)
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    sql = f"""
        SELECT p.i, c.comune
        FROM unnest($1::float8[], $2::float8[])
             WITH ORDINALITY AS p(lon, lat, i)
        LEFT JOIN LATERAL (
            SELECT comune FROM "{schema}".com01012023_g c
            WHERE ST_Contains(
                c.geom, ST_SetSRID(ST_MakePoint(p.lon, p.lat), 4326))
            LIMIT 1
        ) c ON true
        ORDER BY p.i
        """
    try:
        if settings.geoserver_source.db_dsn:
            conn = await asyncpg.connect(dsn)
            try:
                rows = await conn.fetch(sql, lons, lats)
            finally:
                await conn.close()
        else:
            # Il database di Limen (#426): dal pool già aperto, non una
            # connessione nuova per ogni richiesta pubblica di /api/alerts.
            async with acquire() as pooled:
                rows = await pooled.fetch(sql, lons, lats)
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
