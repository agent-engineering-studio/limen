"""``limen fedelta-racconti`` — il revisore serale, lanciato a mano.

Lo stesso controllo del job `limen-fedelta-racconti`, con le stesse regole:
gira solo se `LLM__MODELS__FEDELTA` e `ANTHROPIC_API_KEY` sono dichiarati.
Serve a provarlo senza aspettare lo scheduler.
"""

from __future__ import annotations

from limen.api.jobs.fedelta_racconti import controlla_fedelta
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    try:
        async with lifespan_pool():
            await run_migrations()
            out = await controlla_fedelta(settings)
    finally:
        await SharedHttpClient.aclose()
    log.info("cli.fedelta_racconti.done", **out)
    return 0
