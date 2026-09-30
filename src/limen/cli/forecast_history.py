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
    """Tutti i pericoli abilitati, come il job notturno.

    `LIMEN_FORECAST_HAZARD` la limita a uno — serve a rilanciare a mano il
    solo pericolo che una notte è fallito, senza rifare gli altri.
    """
    import os

    from limen.config.settings import get_settings
    from limen.core.models.hazard import HazardType

    scelto = os.getenv("LIMEN_FORECAST_HAZARD")
    pericoli = [HazardType(scelto)] if scelto else get_settings().hazards.enabled
    total = 0
    async with lifespan_pool():
        await run_migrations()
        for hazard in pericoli:
            celle = await run_forecast_history(hazard=hazard)
            log.info("cli.forecast_history.hazard", hazard=hazard.value, cells=celle)
            total += celle
    log.info("cli.forecast_history.done", cells=total)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
