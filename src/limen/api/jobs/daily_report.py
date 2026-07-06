"""Daily national report — the morning briefing for agent gateways.

Builds the aggregated national picture (:func:`limen.mcp.tools.national_report`)
and dispatches its deterministic Italian rendering through the notification
channels (webhook → OpenClaw, Telegram, …). Informational, not an alert:
no dedup ledger, fires once per schedule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.risk import RiskLevel
from limen.mcp.tools import national_report
from limen.notifications.base import AlertedCell, AlertPayload

log = get_logger(__name__)

_LEVEL_FROM_STRING = {lvl.value: lvl for lvl in RiskLevel}


def build_report_payload(report: dict[str, object]) -> AlertPayload:
    """Wrap the national report in the channel-agnostic payload."""
    top = report["top_cells"] if isinstance(report["top_cells"], list) else []
    cells = [
        AlertedCell(
            cell_id=str(c["cell_id"]),
            score=float(c["score"]),
            level=_LEVEL_FROM_STRING.get(str(c["level"]), RiskLevel.Low),
            priority=float(c["score"]),
        )
        for c in top[:5]
    ]
    max_level = cells[0].level if cells else RiskLevel.None_
    max_score = cells[0].score if cells else 0.0
    return AlertPayload(
        aoi_id="italia",
        max_level=max_level,
        max_score=max_score,
        cells=cells,
        summary_it=str(report["report_it"]),
        pipeline_version="v1-report-daily",
        dispatched_at=datetime.now(UTC),
    )


async def run_daily_report(deps: AppDependencies) -> dict[str, bool]:
    """Build + dispatch the national report; returns per-channel outcomes."""
    report = await national_report()
    payload = build_report_payload(report)
    outcomes = await deps.notification_dispatcher.dispatch(payload)
    log.info(
        "job.daily_report.dispatched",
        regions=report.get("totals"),
        channels=outcomes,
    )
    return outcomes
