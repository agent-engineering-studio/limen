"""Deterministic V1 scoring engine.

Exposes a stable interface so the V2 ML model (later prompt) can be a
drop-in replacement: :func:`score` takes a fully-assembled
:class:`CellFeatureBundle` and returns a :class:`RiskScore` — no I/O,
no LLM, no network. Assembling the bundle from DB/cache is a separate
concern (Phase 4).
"""

from limen.core.scoring.engine import MultiFactorScoringEngine, score
from limen.core.scoring.regional_thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    RegionalThresholds,
    load_regional_thresholds,
)

__all__ = [
    "DEFAULT_THRESHOLDS_PATH",
    "MultiFactorScoringEngine",
    "RegionalThresholds",
    "load_regional_thresholds",
    "score",
]
