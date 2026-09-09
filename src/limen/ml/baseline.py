"""V1-baseline scoring for the same dataset the ML model trains on.

Used by the promotion gate: the ML challenger must beat the V1 baseline
on the exact same spatial-block CV partition before it gets promoted.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from limen.core.models.hazard import HazardType
from limen.core.models.risk import HazardBreakdown
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire.engine import WildfireScoringEngine
from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml.feature_store import features_to_bundle, wildfire_features_to_bundle


def score_with_engine(engine: ScoringEngine[HazardBreakdown], samples: list[TrainingSample]) -> Any:
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


def caine_baseline(samples: list[TrainingSample]) -> Any:
    """Caine I-D power-law only — the triggering-literature reference.

    Uses the engine's normalised Caine exceedance (``caine_norm``) as the
    score: does the ML add value over the bare rainfall threshold, not
    just over the full V1 blend?
    """
    import numpy as np

    engine = MultiFactorScoringEngine()
    out: list[float] = []
    for s in samples:
        bundle = features_to_bundle(
            cell_id=s.cell_id,
            aoi_id="training-replay",
            valuation_time=s.valuation_time,
            features=s.features,
        )
        result = engine.score(bundle)
        out.append(float(result.breakdown.meteo_terms.caine_norm))
    return np.array(out, dtype=float)


def wildfire_baseline(samples: list[TrainingSample]) -> Any:
    """Baseline **FWI-only**: il motore V1 incendio sugli stessi campioni (#68).

    È il riferimento che il challenger deve battere. Un campione senza la
    parte meteo arricchita prende ``nan`` e non 0: contarlo come "nessun
    pericolo" regalerebbe alla baseline i veri negativi che non abbiamo
    misurato, e la renderebbe artificialmente brava proprio dove tace.
    """
    import numpy as np

    thresholds = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(thresholds, WildfireThresholds)
    engine = WildfireScoringEngine(thresholds)
    out: list[float] = []
    for s in samples:
        bundle = wildfire_features_to_bundle(
            cell_id=s.cell_id,
            aoi_id="training-replay",
            valuation_time=s.valuation_time,
            features=s.features,
        )
        out.append(float("nan") if bundle is None else float(engine.score(bundle).score))
    return np.array(out, dtype=float)


def baseline_for(hazard: HazardType) -> Callable[[list[TrainingSample]], Any]:
    """La baseline di un pericolo. Una tabella, non un ramo per chiamante."""
    if hazard is HazardType.WILDFIRE:
        return wildfire_baseline
    return v1_baseline


__all__ = [
    "baseline_for",
    "caine_baseline",
    "score_with_engine",
    "v1_baseline",
    "wildfire_baseline",
]
