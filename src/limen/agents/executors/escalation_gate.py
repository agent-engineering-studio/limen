"""Escalation gate.

V1 tracked the escalation count for observability. V1.5 added the
``hard_escalation`` flag from in-situ sensors. V2.x now also attaches
a typed evidence bundle (``escalation_evidence``) produced by
:func:`build_escalation_evidence`, so the operator can read the
top-K culprit cells + their dominant component without re-parsing
``cell_results`` downstream.

The gate stays a pass-through on the authoritative numbers — it only
*annotates* ``ctx.notes``.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.agents.workflows.escalation_workflow import build_escalation_evidence
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


class EscalationGateExecutor(Executor):
    """Tracks the escalation regime for observability + hard-escalation."""

    def __init__(self, *, evidence_top_k: int = 5) -> None:
        super().__init__(name="EscalationGate")
        self._evidence_top_k = evidence_top_k

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        high = ctx.assessment.cells_high_or_above if ctx.assessment else 0
        hard_cells = [r.cell_id for r in ctx.cell_results if r.hard_escalation]
        evidence = build_escalation_evidence(ctx, top_k=self._evidence_top_k)
        log.info(
            "executor.escalation_gate",
            aoi_id=ctx.aoi_id,
            would_escalate=high > 0,
            high_or_above=high,
            hard_escalation_cells=len(hard_cells),
            evidence_rows=len(evidence),
        )
        notes = dict(ctx.notes)
        notes["escalation_would_trigger"] = high > 0 or bool(hard_cells)
        notes["escalation_high_or_above"] = high
        notes["hard_escalation_cells"] = hard_cells
        notes["escalation_evidence"] = [
            {
                "cell_id": e.cell_id,
                "level": e.level.value,
                "score": e.score,
                "hard_escalation": e.hard_escalation,
                "dominant_component": e.dominant_component,
            }
            for e in evidence
        ]
        return ctx.with_update(notes=notes)
