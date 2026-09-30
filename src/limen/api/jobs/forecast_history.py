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
    """La previsione per cella, per **ogni** pericolo abilitato.

    Girava solo per il pericolo di default, cioè le frane: la colonna dei
    comuni mostrava il futuro di un pericolo su tre, e una cella con
    l'incendio alto non aveva nessuna previsione d'incendio — senza che niente
    lo dicesse, se non una riga in piccolo nella testata. Il workflow
    previsionale sapeva già fare gli altri due: l'alluvione con i suoi trigger
    per nodo, l'incendio camminando la catena FWI fino al giorno previsto
    senza scriverlo (`FwiUpdateExecutor`).

    Un pericolo che fallisce non ferma gli altri: la previsione delle frane
    non deve saltare perché GloFAS ha risposto 429.
    """
    totale = 0
    for hazard in deps.settings.hazards.enabled:
        try:
            totale += await run_forecast_history(settings=deps.settings, hazard=hazard)
        except Exception as exc:
            # Scheduler job must never crash the loop — log and move on.
            log.warning(
                "job.forecast_history.failed",
                hazard=hazard.value,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    return totale
