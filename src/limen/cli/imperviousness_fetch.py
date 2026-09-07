"""``limen imperviousness-fetch`` — scarica il raster CLMS del suolo sigillato.

L'unico layer per cella che restava non ottenibile: la documentazione mandava
a ``land.copernicus.eu``, che chiede un account, e finché non c'era il file
`imperviousness_norm` restava NULL su tutte le celle. Il dato è pubblico
altrove — l'EEA serve lo stesso prodotto su un ImageServer aperto — quindi il
comando lo scarica e basta.

Idempotente: con il file già presente non scarica niente. ``LIMEN_IMPERVIOUSNESS_FORCE=1``
per rifarlo, ``LIMEN_IMPERVIOUSNESS_DEST`` per scriverlo altrove.

Dopo, `LIMEN_IMPERVIOUSNESS_RASTER` va puntato sul file e
``limen bootstrap-static`` riempie le celle: il comando lo stampa, non lo
scrive nell'ambiente, perché nessun comando qui modifica il `.env`.
"""

from __future__ import annotations

import os

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.integrations.imperviousness.fetch import (
    IMPERVIOUSNESS_FORCE_ENV,
    fetch_imperviousness,
)
from limen.integrations.imperviousness.sync_job import IMPERVIOUSNESS_RASTER_ENV

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    force = os.environ.get(IMPERVIOUSNESS_FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}

    async with lifespan_pool(settings.db):
        path = await fetch_imperviousness(force=force)

    if path is None:
        log.error(
            "imperviousness_fetch.no_aoi",
            hint="esegui prima `limen seed`: il riquadro da scaricare viene dalle AOI",
        )
        return 1

    log.info(
        "imperviousness_fetch.done",
        path=str(path),
        next_step=f"{IMPERVIOUSNESS_RASTER_ENV}={path} e poi `limen bootstrap-static`",
    )
    return 0


__all__ = ["run"]
