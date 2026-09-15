"""``limen effis-sync`` — perimetri di area bruciata EFFIS per ogni AOI (#101).

Comando a sé e non un passo dentro `bootstrap-static`, per la stessa ragione
per cui `ingest-events` e `ingest-fire-history` sono comandi a sé: questi sono
**dataset di verità**, non fattori statici per cella. Il bootstrap per cella
non fa nessuna chiamata HTTP, e infilargliene una avrebbe reso ogni suo test
d'integrazione dipendente dalla disponibilità di EFFIS — la lezione della #90,
dove una suite lenta per colpa della rete ha tenuto la CI rossa per due mesi.

Sta però nella **stessa sequenza** (`scripts/load_static_data.sh`), che è ciò
che la #101 chiedeva: il truth set del backtest incendio non deve essere un
passo che qualcuno ricorda.

Idempotente sul costo come il bootstrap, e con lo stesso meccanismo. Una nota
sull'impronta, perché è diversa dalle altre: si calcola sulla tabella che
questo comando **scrive**, non su una sorgente esterna, perché EFFIS non si
può interrogare a costo zero per sapere se è cambiato. Conseguenza:
dopo un sync che porta perimetri nuovi, il giro successivo rifà la fetch una
volta di troppo e poi si assesta. Una richiesta da ~300 KB per regione è un
prezzo accettabile; interrogare EFFIS per decidere se interrogarlo no.
"""

from __future__ import annotations

import os

from limen.cli.bootstrap_static import FORCE_ENV
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos.aoi_repo import get_aoi, list_aoi_ids
from limen.integrations.static_bootstrap import fingerprint

log = get_logger(__name__)

_STEP = "fire_perimeters"


async def run() -> int:
    """Scarica i perimetri per ogni AOI seminata. Non solleva mai."""
    forced = os.environ.get(FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}
    async with lifespan_pool():
        aoi_ids = await list_aoi_ids()
        if not aoi_ids:
            log.warning("effis_sync.no_aois", note="run `limen seed` first")
            return 0

        from limen.integrations.effis.sync_job import run_effis_sync

        for aoi_id in aoi_ids:
            aoi = await get_aoi(aoi_id)
            if aoi is None or aoi.geom is None:
                continue
            gate = await fingerprint.StepGate.create(aoi_id, force=forced)
            fp = await fingerprint.of_tables("fire_perimeters", require_rows=False)
            if not await gate.needs(_STEP, fp):
                continue
            # `.bounds` e non il campo `bbox`: quello e' una geometria, e
            # `run_effis_sync` vuole la tupla (minx, miny, maxx, maxy).
            bbox = aoi.geom.bounds
            try:
                counts = await run_effis_sync(bbox=bbox)
            except Exception as exc:
                # Degradazione: EFFIS giu' non deve far fallire la sequenza
                # degli altri layer. Nessuna versione registrata, quindi il
                # prossimo giro riprova.
                log.warning(
                    "effis_sync.failed",
                    aoi_id=aoi_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue
            log.info("effis_sync.done", aoi_id=aoi_id, **counts)
            await gate.done(_STEP, **counts)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
