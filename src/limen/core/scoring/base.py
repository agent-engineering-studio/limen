"""Scoring-engine Protocol (V1 + V2 share this surface).

Both :class:`MultiFactorScoringEngine` (V1 deterministic) and
:class:`MLScoringEngine` (V2) satisfy this Protocol — anything the
workflow holds is typed against it, never the concrete class. That's
what makes the V2 engine a true drop-in: switching
``SCORING__ENGINE=ml`` doesn't ripple through the workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from limen.core.models.risk import BreakdownT_co, CellFeatureBundle, RiskLevel, RiskScore

if TYPE_CHECKING:
    from limen.core.scoring.regional_thresholds import ClassCutoffs


def classify_score(score: float, cutoffs: ClassCutoffs) -> RiskLevel:
    """Map a score in [0, 1] onto the five classes.

    Hazard-agnostic on purpose: every engine produces the same unit scale and
    reads its own cutoffs from its own YAML, so the boundary logic is shared
    even though not a single number is.
    """
    if score < cutoffs.low.lo:
        return RiskLevel.None_
    if score < cutoffs.moderate.lo:
        return RiskLevel.Low
    if score < cutoffs.high.lo:
        return RiskLevel.Moderate
    if score < cutoffs.very_high.lo:
        return RiskLevel.High
    return RiskLevel.VeryHigh


@runtime_checkable
class ScoringEngine(Protocol[BreakdownT_co]):
    """Pure ``bundle → RiskScore`` mapping. No I/O. No network. No LLM.

    Parameterised by the hazard's breakdown shape. A consumer that reads the
    landslide components asks for ``ScoringEngine[ComponentBreakdown]`` and
    keeps full typing; the engine registry, which holds engines for several
    hazards, asks for ``ScoringEngine[HazardBreakdown]`` and sees only the
    discriminator. The parameter is covariant, so the first is assignable to
    the second.
    """

    def score(self, bundle: CellFeatureBundle) -> RiskScore[BreakdownT_co]: ...


__all__ = ["ScoringEngine", "classify_score"]
