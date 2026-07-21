"""Scheduled forecast-trend persistence (issue #41).

Every ``FORECAST__INTERVAL_HOURS`` sweep each AOI at +24/+48/+72 h and store the
≥Moderate cells in ``risk_assessments`` (horizon ``+Hh``) so the sidebar and
report can draw the past+forecast trend. Idempotent (delete-prior); no alerts,
no LLM. Best-effort: a failure is logged, never raised into the scheduler.
"""

from __future__ import annotations

from limen.agents.workflows.forecast_history import run_forecast_history
from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger

log = get_logger(__name__)


async def run_forecast_history_job(deps: AppDependencies) -> int:
    try:
        return await run_forecast_history(settings=deps.settings)
    except Exception as exc:  # noqa: BLE001 - scheduler job must not crash the loop
        log.warning("job.forecast_history.failed", error=str(exc), error_type=type(exc).__name__)
        return 0
