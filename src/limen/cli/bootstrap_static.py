"""``limen bootstrap-static`` — one-shot static-factor bootstrap."""

from __future__ import annotations

import os
import sys

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations.osm import sync_osm_infrastructure
from limen.integrations.static_bootstrap import bootstrap_static_for_aoi

log = get_logger(__name__)

#: Ricalcola tutto ignorando le impronte. Variabile e non solo flag perche'
#: `make up` invoca il comando senza argomenti.
FORCE_ENV = "LIMEN_BOOTSTRAP_FORCE"


async def run(*, force: bool = False) -> int:
    """Apply pending migrations, then run static bootstrap for every AOI.

    ``force`` (o ``LIMEN_BOOTSTRAP_FORCE=1``) ricalcola ogni passo anche se la
    sorgente non e' cambiata: serve quando cambia qualcosa che l'impronta non
    vede (#101).
    """
    async with lifespan_pool():
        await run_migrations()
        aois = await list_aoi_ids()
        if not aois:
            log.warning("bootstrap_static.no_aois", note="run `limen seed` first")
            return 0
        # La rete OSM è nazionale: si carica una volta sola, prima del
        # giro per-AOI che ne calcola le distanze.
        await sync_osm_infrastructure()
        forced = force or os.environ.get(FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}
        if forced:
            log.info("bootstrap_static.force", reason=f"{FORCE_ENV} o --force")
        lines: list[str] = []
        for aoi_id in aois:
            result = await bootstrap_static_for_aoi(aoi_id, force=forced)
            log.info(
                "bootstrap_static.aoi.done",
                aoi_id=aoi_id,
                cells_with_factors=result.cells_with_factors,
                recomputed=result.recomputed,
                skipped=result.skipped,
            )
            lines.append(result.summary)
        # Su stdout e non solo nei log: `make up` lo mostra a chi sta
        # guardando il terminale, ed e' li' che serve sapere che non ha
        # ricalcolato niente.
        for line in lines:
            sys.stdout.write(f"[bootstrap] {line}\n")
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
