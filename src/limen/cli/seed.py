"""``limen seed`` — apply migrations then load Puglia + Basilicata AOIs + grids."""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import close_pool, init_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import count_grid_cells, generate_and_store_grid
from limen.data.seed.loader import load_all

log = get_logger(__name__)


async def run() -> int:
    await init_pool()
    try:
        applied = await run_migrations()
        log.info("seed.migrations.applied", files=applied, count=len(applied))

        for aoi in load_all():
            await upsert_aoi(
                id=aoi.id,
                name=aoi.name,
                kind=aoi.kind,
                geom=aoi.geom,
                metadata=aoi.metadata,
            )
            inserted = await generate_and_store_grid(aoi.id)
            total = await count_grid_cells(aoi.id)
            log.info(
                "seed.aoi.loaded",
                aoi_id=aoi.id,
                aoi_name=aoi.name,
                cells_inserted=inserted,
                cells_total=total,
            )
    finally:
        await close_pool()

    log.info("seed.done")
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
