"""`limen sync-egms` — refresh ``cell_insar_features`` for every AOI."""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations.egms import sync_egms

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    async with lifespan_pool(settings.db):
        await run_migrations()
        aois = await list_aoi_ids()
        if not aois:
            log.warning("sync_egms.no_aois")
            return 0
        total = 0
        for aoi_id in aois:
            written = await sync_egms(aoi_id=aoi_id, settings=settings)
            log.info("sync_egms.aoi_done", aoi_id=aoi_id, rows_written=written)
            total += written
        log.info("sync_egms.done", aois=len(aois), rows_written=total)
    return 0
