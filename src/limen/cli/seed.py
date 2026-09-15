"""``limen seed`` — apply migrations then load the ISTAT AOIs + their grids."""

from __future__ import annotations

from collections.abc import Sequence

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import count_grid_cells, generate_and_store_grid
from limen.data.seed.loader import load_all

log = get_logger(__name__)


async def run(*, only: Sequence[str] | None = None) -> int:
    """Apply migrations, then load the seed AOIs and generate their grids.

    ``only`` restringe l'insieme agli id indicati. Serve ai test (#90): la
    griglia a 1 km delle venti regioni sono ~312.000 celle e una ventina di
    minuti, e quasi nessun test di integrazione ha bisogno dell'Italia — ne
    vuole una regione, spesso per poi ridurla a sei celle. Il default resta
    l'intero seme nazionale, quindi `limen seed` non cambia comportamento.
    """
    wanted = set(only) if only is not None else None
    async with lifespan_pool():
        applied = await run_migrations()
        log.info("seed.migrations.applied", files=applied, count=len(applied))

        selected = [a for a in load_all() if wanted is None or a.id in wanted]
        if wanted is not None:
            missing = wanted - {a.id for a in selected}
            if missing:
                # Un id sbagliato deve fermarsi qui: seminare in silenzio meno
                # regioni di quelle chieste darebbe test che passano su un
                # database vuoto.
                raise KeyError(f"unknown seed AOI(s): {', '.join(sorted(missing))}")

        for aoi in selected:
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

    log.info("seed.done")
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
