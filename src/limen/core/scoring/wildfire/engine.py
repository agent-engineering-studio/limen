"""Deterministic wildfire engine (#61).

    score = w_fwi · fwi_norm + w_fuel · fuel + w_slope · slope

Three terms, because three independent things have to be true at once for a
cell to be dangerous: the weather has to be right for fire (FWI), there has
to be something to burn (fuel), and the terrain has to let it run (slope).

A weighted sum rather than a product: a product would zero the score of a
bare-rock cell in extreme fire weather, and a cell next to it *will* burn.
The weights say how much each term matters, and they live in the YAML.

Pure, like the landslide engine: no DB, no network, no LLM. The recursive FWI
codes arrive already advanced in ``bundle.dynamic.fire_weather`` -- persisting
and stepping them is the workflow's job, not the engine's.
"""

from __future__ import annotations

from limen.core.models.risk import (
    CellFeatureBundle,
    RiskScore,
    WildfireBreakdown,
)
from limen.core.scoring.base import classify_score
from limen.core.scoring.regional_thresholds import WildfireThresholds


class WildfireScoringEngine:
    """``ScoringEngine[WildfireBreakdown]`` — the V1 baseline for wildfire."""

    def __init__(self, thresholds: WildfireThresholds) -> None:
        self._t = thresholds

    @property
    def model_version(self) -> str:
        return self._t.model_version

    def score(self, bundle: CellFeatureBundle) -> RiskScore[WildfireBreakdown]:
        t = self._t
        fw = bundle.dynamic.fire_weather

        # No chain for this cell: the danger term is unknown, not zero. Fuel
        # and slope still describe a real predisposition, so the cell keeps a
        # score instead of going dark -- but with fwi_norm at 0 it can never
        # reach the top classes, which is the honest answer when the only
        # time-varying input is missing.
        fwi_norm = 0.0 if fw is None else min(fw.fwi / t.fwi.normalisation_max, 1.0)

        fuel = t.fuel.for_code(bundle.static.landuse_code)

        slope_deg = bundle.static.slope_deg
        slope = 0.0 if slope_deg is None else min(slope_deg / t.slope.saturation_deg, 1.0)

        score = min(
            t.weights.fwi * fwi_norm + t.weights.fuel * fuel + t.weights.slope * slope,
            1.0,
        )
        return RiskScore[WildfireBreakdown](
            score=score,
            level=classify_score(score, t.classes),
            breakdown=WildfireBreakdown(
                fwi_norm=fwi_norm,
                fuel=fuel,
                slope=slope,
                fire_weather=fw,
                spinup=fw is not None and fw.chain_days < t.fwi.spinup_days,
            ),
            model_version=t.model_version,
        )


__all__ = ["WildfireScoringEngine"]
