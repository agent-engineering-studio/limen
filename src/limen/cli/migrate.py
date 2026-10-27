"""``limen migrate`` — apply pending SQL migrations."""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import crea_database_mlflow, imposta_password_dei_ruoli, run_migrations

log = get_logger(__name__)


async def run() -> int:
    """Initialise the pool (if not already), apply migrations, close on exit."""
    async with lifespan_pool():
        applied = await run_migrations()
        settings = get_settings()
        await imposta_password_dei_ruoli(settings)
        await crea_database_mlflow(settings)
    log.info("cli.migrate.done", applied=applied)
    return 0


def main() -> int:  # convenience for pyproject entry points
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
