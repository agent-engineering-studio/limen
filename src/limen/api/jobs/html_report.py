"""Job periodico: genera il report HTML statico (build al boot + ogni N ore).

Degrada in modo neutro: un errore nel build non deve mai far cadere lo
scheduler né lo startup. Ritorna uno status per il logging.
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.report.builder import build_report

log = get_logger(__name__)


async def run_html_report(deps: AppDependencies) -> dict[str, object]:
    try:
        result = await build_report(deps.settings)
    except Exception as exc:  # il job non deve mai propagare
        log.warning("job.html_report.failed", error=str(exc), error_type=type(exc).__name__)
        return {"ok": False, "error": str(exc)}
    log.info("job.html_report.done", build=str(result) if result else None)
    return {"ok": True, "build": str(result) if result else None}
