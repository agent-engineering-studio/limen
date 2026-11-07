"""``limen seed`` — apply migrations then load the ISTAT AOIs + their grids."""

from __future__ import annotations

from collections.abc import Sequence

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import count_grid_cells, generate_and_store_grid
from limen.data.seed.loader import SeedAOI, load_all

log = get_logger(__name__)


async def run(*, only: Sequence[str] | None = None) -> int:
    """Apply migrations, then load the seed AOIs and generate their grids.

    ``only`` restringe l'insieme agli id indicati. Serve ai test (#90): la
    griglia a 1 km delle venti regioni sono ~312.000 celle e una ventina di
    minuti, e quasi nessun test di integrazione ha bisogno dell'Italia — ne
    vuole una regione, spesso per poi ridurla a sei celle. Senza ``only``
    decide ``INSTALLAZIONE__REGIONI`` (#407), e vuota resta l'Italia intera.
    """
    if only is None:
        only = get_settings().installazione.regioni_scelte
    async with lifespan_pool():
        applied = await run_migrations()
        log.info("seed.migrations.applied", files=applied, count=len(applied))
        await semina(scegli(only))

    log.info("seed.done")
    return 0


def scegli(only: Sequence[str] | None) -> list[SeedAOI]:
    """Le AOI del seme con quegli id; tutte con ``None``.

    Un id sbagliato si ferma qui: seminare in silenzio meno regioni di quelle
    chieste darebbe test che passano su un database vuoto, e un'installazione
    che monitora la regione sbagliata.
    """
    tutte = load_all()
    if only is None:
        return tutte
    wanted = set(only)
    missing = wanted - {a.id for a in tutte}
    if missing:
        raise KeyError(f"unknown seed AOI(s): {', '.join(sorted(missing))}")
    return [a for a in tutte if a.id in wanted]


async def semina(aois: Sequence[SeedAOI]) -> None:
    """Le AOI e le loro griglie, a pool aperto. Idempotente."""
    for aoi in aois:
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


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
