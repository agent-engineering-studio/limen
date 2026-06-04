"""V1-baseline scoring for the same dataset the ML model trains on.

Used by the promotion gate: the ML challenger must beat the V1 baseline
on the exact same spatial-block CV partition before it gets promoted.
"""

from __future__ import annotations

from typing import Any

from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml.feature_store import features_to_bundle


def score_with_engine(engine: ScoringEngine, samples: list[TrainingSample]) -> Any:
    """Return an ``np.ndarray`` of V1 scores for each training sample."""
    import numpy as np

    aoi_id_default = "training-replay"
    out: list[float] = []
    for s in samples:
        bundle = features_to_bundle(
            cell_id=s.cell_id,
            aoi_id=aoi_id_default,
            valuation_time=s.valuation_time,
            features=s.features,
        )
        result = engine.score(bundle)
        out.append(float(result.score))
    return np.array(out, dtype=float)


def v1_baseline(samples: list[TrainingSample]) -> Any:
    """V1 deterministic baseline scores."""
    return score_with_engine(MultiFactorScoringEngine(), samples)


__all__ = ["score_with_engine", "v1_baseline"]
