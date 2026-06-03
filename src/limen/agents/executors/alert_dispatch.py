"""Alert-dispatch executor — V1 logging stub.

Real Telegram / MQTT / Email channels land in Phase 7. V1 logs the
dispatched alert intent so observability/CI can verify the workflow
reached this stage.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import RiskLevel

log = get_logger(__name__)


def _level_rank(level: RiskLevel) -> int:
    order = (
        RiskLevel.None_,
        RiskLevel.Low,
        RiskLevel.Moderate,
        RiskLevel.High,
        RiskLevel.VeryHigh,
    )
    return order.index(level)


class AlertDispatchExecutor(Executor):
    """Logs the intended alerts; the real channels arrive in Phase 7."""

    def __init__(self, *, alert_threshold: RiskLevel = RiskLevel.High) -> None:
        super().__init__(name="AlertDispatch")
        self._threshold = alert_threshold

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        threshold_rank = _level_rank(self._threshold)
        to_alert = [r for r in ctx.cell_results if _level_rank(r.level) >= threshold_rank]
        dispatched: list[str] = []
        for cell in to_alert:
            payload = (
                f"limen-alert aoi={ctx.aoi_id} cell={cell.cell_id} "
                f"score={cell.score:.3f} level={cell.level.value}"
            )
            log.info("executor.alert_dispatch.stub", payload=payload)
            dispatched.append(payload)
        log.info(
            "executor.alert_dispatch",
            aoi_id=ctx.aoi_id,
            cells_to_alert=len(to_alert),
            threshold=self._threshold.value,
        )
        return ctx.with_update(dispatched_alerts=dispatched)
