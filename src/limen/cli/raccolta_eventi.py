"""``limen raccolta-eventi`` — la raccolta degli eventi dalla stampa, a mano.

Lo stesso lavoro del job `limen-raccolta-eventi` (#347), con le stesse regole:
gira solo se `LLM__MODELS__EVENTI` e `ANTHROPIC_API_KEY` sono dichiarati.
"""

from __future__ import annotations

from limen.api.jobs.raccolta_eventi import raccogli
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
            out = await raccogli(settings)
    finally:
        await SharedHttpClient.aclose()
    log.info("cli.raccolta_eventi.done", **out)
    return 0
