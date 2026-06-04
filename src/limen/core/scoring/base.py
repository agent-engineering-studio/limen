"""Scoring-engine Protocol (V1 + V2 share this surface).

Both :class:`MultiFactorScoringEngine` (V1 deterministic) and
:class:`MLScoringEngine` (V2) satisfy this Protocol — anything the
workflow holds is typed against it, never the concrete class. That's
what makes the V2 engine a true drop-in: switching
``SCORING__ENGINE=ml`` doesn't ripple through the workflow.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from limen.core.models.risk import CellFeatureBundle, RiskScore


@runtime_checkable
class ScoringEngine(Protocol):
    """Pure ``bundle → RiskScore`` mapping. No I/O. No network. No LLM."""

    def score(self, bundle: CellFeatureBundle) -> RiskScore: ...


__all__ = ["ScoringEngine"]
