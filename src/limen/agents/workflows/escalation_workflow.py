"""Escalation sub-workflow — fan-out evidence collector on High+ cells.

The main workflow's :class:`EscalationGateExecutor` is a logger; the
escalation *sub-workflow* is the operational follow-up: when at least
one cell crosses the High/VeryHigh threshold (or carries the V1.5
hard-escalation flag), this function returns a short list of
``(cell_id, summary)`` evidence rows the operator can hand to a peer
review.

The sub-workflow is intentionally *pure* — it reads the same
:class:`MonitoringContext` the main workflow produced and returns a
typed evidence bundle. No I/O, no LLM, no new DB writes. Persistence
+ alert dispatch happen in the main pipeline; the escalation surface
only summarises what was already computed.

Tests assert the function is deterministic and never invents numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.models.risk import RiskLevel


@dataclass(frozen=True, slots=True)
class EscalationEvidence:
    """One row in the escalation bundle.

    Fields mirror what the operator needs to triage in 30 seconds:
    cell id, the deterministic level + score, whether it tripped the
    V1.5 hard-escalation flag, and a one-line driver hint from the
    breakdown (which component contributed most).
    """

    cell_id: str
    level: RiskLevel
    score: float
    hard_escalation: bool
    dominant_component: str


_COMPONENTS: tuple[str, ...] = ("S", "M", "E", "F", "H", "K")


def _dominant_component(record: CellRiskRecord) -> str:
    """Return the single-letter id of the component with the highest contribution.

    Ties resolve in the order ``_COMPONENTS`` is declared; ``K`` only
    surfaces when V1.5 hard escalation pushed it above the others.
    """
    contributions = {
        "S": float(record.s),
        "M": float(record.m),
        "E": float(record.e),
        "F": float(record.f),
        "H": float(record.h),
        "K": float(getattr(record, "k", 0.0) or 0.0),
    }
    best = "S"
    best_value = -1.0
    # Iterate in declaration order so ties are deterministic.
    for label in _COMPONENTS:
        value = contributions.get(label, 0.0)
        if value > best_value:
            best = label
            best_value = value
    return best


_ESCALATION_LEVELS = (RiskLevel.High, RiskLevel.VeryHigh)


def _is_escalated(record: CellRiskRecord) -> bool:
    if record.level in _ESCALATION_LEVELS:
        return True
    # V1.5 hard escalation: kinematic alarm bypasses the level threshold.
    return bool(getattr(record, "hard_escalation", False))


def build_escalation_evidence(
    context: MonitoringContext, *, top_k: int = 5
) -> list[EscalationEvidence]:
    """Return up to ``top_k`` evidence rows, ordered by descending score.

    Empty list when no cell crosses the gate — the caller treats that
    as "nothing to escalate, the main flow is sufficient".
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1: {top_k}")
    candidates = [r for r in context.cell_results if _is_escalated(r)]
    candidates.sort(key=lambda r: r.score, reverse=True)
    return [
        EscalationEvidence(
            cell_id=r.cell_id,
            level=r.level,
            score=float(r.score),
            hard_escalation=bool(getattr(r, "hard_escalation", False)),
            dominant_component=_dominant_component(r),
        )
        for r in candidates[:top_k]
    ]


def build_escalation_workflow() -> None:
    """Reserved for the MAF-style sub-workflow fan-out (V2+).

    Kept as a no-op factory so the import path stays stable.
    """
    return None


__all__ = [
    "EscalationEvidence",
    "build_escalation_evidence",
    "build_escalation_workflow",
]
