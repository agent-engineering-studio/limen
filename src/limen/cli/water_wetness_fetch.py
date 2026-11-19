"""``limen water-wetness-fetch`` — scarica l'HRL WaterWetness 2018 (#420).

Idempotente: con il file già presente non scarica niente.
``LIMEN_WATER_WETNESS_FORCE=1`` per rifarlo, ``LIMEN_WATER_WETNESS_DEST`` per
scriverlo altrove. Dopo, `LIMEN_WATER_WETNESS_RASTER` va puntato sul file e
``limen bootstrap-static`` riempie le celle: il comando lo dice, non lo scrive
nel `.env`.
"""

from __future__ import annotations

import os

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.integrations.water_wetness.fetch import WATER_WETNESS_FORCE_ENV, fetch_water_wetness
from limen.integrations.water_wetness.sync_job import WATER_WETNESS_RASTER_ENV

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    force = os.environ.get(WATER_WETNESS_FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}

    async with lifespan_pool(settings.db):
        path = await fetch_water_wetness(force=force)

    if path is None:
        log.error(
            "water_wetness_fetch.no_aoi",
            hint="esegui prima `limen seed`: il riquadro da scaricare viene dalle AOI",
        )
        return 1

    log.info(
        "water_wetness_fetch.done",
        path=str(path),
        next_step=f"{WATER_WETNESS_RASTER_ENV}={path} e poi `limen bootstrap-static`",
    )
    return 0


__all__ = ["run"]
