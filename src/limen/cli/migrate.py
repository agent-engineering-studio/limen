"""``limen migrate`` — apply pending SQL migrations."""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import close_pool, init_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)


async def run() -> int:
    """Initialise the pool, apply migrations, and close the pool."""
    await init_pool()
    try:
        applied = await run_migrations()
    finally:
        await close_pool()
    log.info("cli.migrate.done", applied=applied)
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
