"""``limen dpc-bollettini`` — importa l'ultimo bollettino di criticità DPC."""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc.sync_bollettini import run_sync_bollettini

log = get_logger(__name__)


async def run() -> int:
    async with lifespan_pool():
        esito = await run_sync_bollettini()
    await SharedHttpClient.aclose()
    log.info("cli.dpc_bollettini.done", **esito)
    return 0
