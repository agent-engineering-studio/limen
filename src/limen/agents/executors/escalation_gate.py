"""Escalation gate.

Pass-through in V1 — tracks the escalation count for observability.
V1.5 additionally records the cells flagged with ``hard_escalation``
on the per-cell breakdown so the downstream AlertDispatch can fire on
them even if they sit below the ``min_level`` threshold.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


class EscalationGateExecutor(Executor):
    """Tracks the escalation regime for observability + hard-escalation."""

    def __init__(self) -> None:
        super().__init__(name="EscalationGate")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        high = ctx.assessment.cells_high_or_above if ctx.assessment else 0
        hard_cells = [r.cell_id for r in ctx.cell_results if r.hard_escalation]
        log.info(
            "executor.escalation_gate",
            aoi_id=ctx.aoi_id,
            would_escalate=high > 0,
            high_or_above=high,
            hard_escalation_cells=len(hard_cells),
        )
        notes = dict(ctx.notes)
        notes["escalation_would_trigger"] = high > 0 or bool(hard_cells)
        notes["escalation_high_or_above"] = high
        notes["hard_escalation_cells"] = hard_cells
        return ctx.with_update(notes=notes)
