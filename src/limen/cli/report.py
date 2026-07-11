"""``limen report build`` — genera il report HTML statico una volta (idempotente).

Mirrors the pool-init / migration / shared-HTTP-client lifecycle used by the
other standalone CLI runners (see ``limen.cli.backtest`` / ``monitor_once``):
``build_report`` assumes an already-open asyncpg pool and lazily opens the
shared httpx client (for basemap tile fetches in the cluster snapshots), so
this wrapper owns both for the lifetime of the run.
"""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.integrations._http import SharedHttpClient
from limen.report.builder import build_report

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    try:
        async with lifespan_pool():
            await run_migrations()
            result = await build_report(settings)
    finally:
        await SharedHttpClient.aclose()
    log.info("cli.report.done", build=str(result) if result is not None else "skipped")
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
