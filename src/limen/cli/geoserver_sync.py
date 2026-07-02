"""``limen geoserver-sync`` — load ISPRA static data from GeoServer PostGIS.

Refreshes the operational ``iffi_landslides`` / ``pai_hazard`` tables from
the GeoServer-backed PostGIS (``GEOSERVER_SOURCE__DB_DSN``) for every seeded
AOI. A no-op when the DSN is unset. Run ``limen bootstrap-static`` afterwards
(or instead — it calls this loader first) to recompute the per-cell factors.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations.geoserver_source import sync_geoserver_source_for_aoi

log = get_logger(__name__)


async def run() -> int:
    async with lifespan_pool():
        await run_migrations()
        aois = await list_aoi_ids()
        if not aois:
            log.warning("geoserver_sync.no_aois", note="run `limen seed` first")
            return 0
        for aoi_id in aois:
            counts = await sync_geoserver_source_for_aoi(aoi_id)
            log.info("geoserver_sync.aoi.done", aoi_id=aoi_id, **counts)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
