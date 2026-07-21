"""``limen forecast-history`` — persist per-cell forecast trend (issue #41).

Sweeps every AOI at +24/+48/+72 h and stores the ≥Moderate cells in
``risk_assessments`` so the sidebar / report can draw the past+forecast trend.
Idempotent (delete-prior). Schedule periodically for a fresh forecast tail.
"""

from __future__ import annotations

from limen.agents.workflows.forecast_history import run_forecast_history
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)


async def run() -> int:
    async with lifespan_pool():
        await run_migrations()
        total = await run_forecast_history()
    log.info("cli.forecast_history.done", cells=total)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
