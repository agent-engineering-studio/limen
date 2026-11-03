"""`limen esposizione-sync` — l'esposizione ISPRA per comune, subito.

Lo stesso lavoro del passo notturno `esposizione_ispra`, a comando: su un
server nuovo riempie `esposizione_comuni` senza aspettare la notte (~70 s la
prima volta, poi i file su disco valgono un mese).
"""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.integrations.idrogeo.esposizione import sync_esposizione

log = get_logger(__name__)


async def run() -> int:
    async with lifespan_pool(get_settings().db):
        await run_migrations()
        esito = await sync_esposizione()
    log.info("esposizione_sync.done", **esito)
    return 0
