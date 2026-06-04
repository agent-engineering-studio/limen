"""``limen bootstrap-static`` — one-shot static-factor bootstrap."""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations.static_bootstrap import bootstrap_static_for_aoi

log = get_logger(__name__)


async def run() -> int:
    """Apply pending migrations, then run static bootstrap for every AOI."""
    async with lifespan_pool():
        await run_migrations()
        aois = await list_aoi_ids()
        if not aois:
            log.warning("bootstrap_static.no_aois", note="run `limen seed` first")
            return 0
        for aoi_id in aois:
            result = await bootstrap_static_for_aoi(aoi_id)
            log.info("bootstrap_static.aoi.done", aoi_id=aoi_id, **result)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
