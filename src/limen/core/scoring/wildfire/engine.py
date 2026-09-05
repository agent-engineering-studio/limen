"""Deterministic wildfire engine (#61).

    score = fwi_norm × (w_base + w_fuel · fuel + w_slope · slope)

The terrain **modulates** the weather rather than adding to it. Three
independent things have to be true at once for a cell to be dangerous: the
weather has to be right for fire, there has to be something to burn, and the
slope has to let it run -- but the weather is the gate. A sum would give a
conifer forest a weather-independent floor, so it would read "Moderate" under
a January downpour, which is physically false.

``w_base`` is why this is not a plain product: it is the share of the danger
a cell carries because fire arrives from *outside* it, so bare rock in
extreme fire weather still scores. The three weights sum to 1, which makes a
maximally flammable, maximally steep cell score exactly its normalised FWI --
that is what keeps the class cutoffs readable as EFFIS danger bands.

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

        # No chain: the weather term is *unknown*, and with a multiplicative
        # form that leaves nothing to say. The cell scores zero and the
        # breakdown says the chain is untrustworthy -- a dark cell that
        # declares why beats a plausible number nobody can source.
        fwi_norm = 0.0 if fw is None else min(fw.fwi / t.fwi.normalisation_max, 1.0)

        fuel = t.fuel.for_code(bundle.static.landuse_code)

        slope_deg = bundle.static.slope_deg
        slope = 0.0 if slope_deg is None else min(slope_deg / t.slope.saturation_deg, 1.0)

        terrain = t.weights.base + t.weights.fuel * fuel + t.weights.slope * slope
        score = min(fwi_norm * terrain, 1.0)
        return RiskScore[WildfireBreakdown](
            score=score,
            level=classify_score(score, t.classes),
            breakdown=WildfireBreakdown(
                fwi_norm=fwi_norm,
                fuel=fuel,
                slope=slope,
                fire_weather=fw,
                # A missing chain is the extreme case of an untrustworthy one,
                # not a separate state: flagging only the short chains would
                # report the worst case as settled.
                spinup=fw is None or fw.chain_days < t.fwi.spinup_days,
            ),
            model_version=t.model_version,
        )


__all__ = ["WildfireScoringEngine"]
