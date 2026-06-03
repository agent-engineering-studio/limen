"""Escalation gate — V1 pass-through.

V1.5+ branches a concurrent sub-workflow whenever a cell crosses the
High/VeryHigh threshold (fan-out to a Risk-Analyst peer + persistence
of corroborating evidence). V1 simply records *whether* the gate would
have triggered, so observability sees the would-be branches without
actually fanning out.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


class EscalationGateExecutor(Executor):
    """Pass-through in V1; tracks the escalation count for observability."""

    def __init__(self) -> None:
        super().__init__(name="EscalationGate")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        high = ctx.assessment.cells_high_or_above if ctx.assessment else 0
        log.info(
            "executor.escalation_gate",
            aoi_id=ctx.aoi_id,
            would_escalate=high > 0,
            high_or_above=high,
        )
        notes = dict(ctx.notes)
        notes["escalation_would_trigger"] = high > 0
        notes["escalation_high_or_above"] = high
        return ctx.with_update(notes=notes)
