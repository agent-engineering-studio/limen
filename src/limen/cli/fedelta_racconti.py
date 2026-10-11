"""``limen fedelta-racconti`` — il revisore serale, lanciato a mano.

Lo stesso controllo del job `limen-fedelta-racconti`, con le stesse regole:
gira solo se `LLM__MODELS__FEDELTA` è dichiarato e, se il modello è lento,
solo dentro `LLM__SLOW_MODELS_WINDOW_UTC`. Serve a provarlo stasera senza
aspettare lo scheduler.
"""

from __future__ import annotations

from limen.agents.llm_factory.resolver import resolve_llm_factory
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
            out = await controlla_fedelta(settings, resolve_llm_factory(settings))
    finally:
        await SharedHttpClient.aclose()
    log.info("cli.fedelta_racconti.done", **out)
    return 0
