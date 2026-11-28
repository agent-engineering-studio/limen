"""Deterministic V1 scoring engine.

Exposes a stable interface so the V2 ML model (later prompt) can be a
drop-in replacement: :func:`score` takes a fully-assembled
:class:`CellFeatureBundle` and returns a :class:`RiskScore` — no I/O,
no LLM, no network. Assembling the bundle from DB/cache is a separate
concern (Phase 4).
"""

from limen_core.models.hazard import DEFAULT_HAZARD

from limen.core.scoring.engine import MultiFactorScoringEngine, score
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    hazard_thresholds_path,
    load_regional_thresholds,
)

#: Il file delle soglie frana, in `limen.config`: `limen/__init__.py` ha già
#: detto a limen-core dov'è la taratura.
DEFAULT_THRESHOLDS_PATH = hazard_thresholds_path(DEFAULT_HAZARD)

__all__ = [
    "DEFAULT_THRESHOLDS_PATH",
    "MultiFactorScoringEngine",
    "RegionalThresholds",
    "load_regional_thresholds",
    "score",
]
