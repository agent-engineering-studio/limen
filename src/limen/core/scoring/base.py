"""Scoring-engine Protocol (V1 + V2 share this surface).

Both :class:`MultiFactorScoringEngine` (V1 deterministic) and
:class:`MLScoringEngine` (V2) satisfy this Protocol — anything the
workflow holds is typed against it, never the concrete class. That's
what makes the V2 engine a true drop-in: switching
``SCORING__ENGINE=ml`` doesn't ripple through the workflow.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from limen.core.models.risk import BreakdownT_co, CellFeatureBundle, RiskScore


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


__all__ = ["ScoringEngine"]
