"""``limen seed-comuni`` — import ISTAT comune boundaries into the operational
DB and tag every grid cell with its comune (static, idempotent).

Reads the boundaries once from the GeoServer PostGIS (GEOSERVER_SOURCE__DB_DSN);
nothing queries that DB in the hot path afterwards. Comuni whose centroid falls
outside every seeded AOI are skipped (keeps the table to seeded regions).
"""

from __future__ import annotations

import asyncpg

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)

_SRC_SQL = """
SELECT pro_com_t::text AS istat_code, comune AS name,
       ST_AsBinary(ST_Multi(ST_Force2D(ST_Transform(geom, 4326)))) AS wkb
FROM com01012023_g
WHERE geom IS NOT NULL
"""


async def run() -> int:
    settings = get_settings()
    dsn = settings.geoserver_source.db_dsn
    if not dsn:
        log.error("cli.seed_comuni.no_dsn", need="GEOSERVER_SOURCE__DB_DSN")
        return 2

    src = await asyncpg.connect(dsn)
    try:
        rows = await src.fetch(_SRC_SQL)
    finally:
        await src.close()

    tagged = 0
    async with lifespan_pool():
        await run_migrations()
        inserted = 0
        async with acquire() as conn, conn.transaction():
            for r in rows:
                # aoi_id via spatial containment against seeded AOIs; skip
                # comuni outside every seeded region.
                res = await conn.execute(
                    """
                    INSERT INTO comuni (istat_code, name, aoi_id, geom)
                    SELECT $1, $2, a.id, ST_SetSRID(ST_GeomFromWKB($3), 4326)
                    FROM aoi a
                    WHERE ST_Contains(
                        a.geom, ST_PointOnSurface(ST_SetSRID(ST_GeomFromWKB($3), 4326)))
                    LIMIT 1
                    ON CONFLICT (istat_code) DO UPDATE
                        SET name = EXCLUDED.name, aoi_id = EXCLUDED.aoi_id,
                            geom = EXCLUDED.geom
                    """,
                    r["istat_code"],
                    r["name"],
                    r["wkb"],
                )
                if res.split()[-1] == "1":
                    inserted += 1
            # Tag cells (static): comune contains cell centroid.
            await conn.execute(
                """
                INSERT INTO cell_comune (cell_id, istat_code)
                SELECT g.id, c.istat_code
                FROM grid_cells g
                JOIN comuni c ON ST_Contains(c.geom, g.centroid)
                ON CONFLICT (cell_id) DO UPDATE SET istat_code = EXCLUDED.istat_code
                """
            )
            tagged = await conn.fetchval("SELECT COUNT(*) FROM cell_comune")
        async with acquire() as conn:
            # First-time comune-matview population + the 312k-row latest refresh
            # blow past the pool's default command timeout; give it room.
            rc = await conn.fetchval("SELECT refresh_mv_latest_risk()", timeout=600)
    log.info("cli.seed_comuni.done", comuni=inserted, cells_tagged=tagged, refresh=rc)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
