"""Deterministic flood engine (#63).

    score = susceptibilità × max(pluviale, fluviale)

**A maximum, not a sum.** The two triggers are different ways for the same
cell to end up under water; a cell is not more flooded because both could
happen. Whichever is worse is what an operator has to plan for, and summing
them would let two moderate signals invent a severe one.

**Susceptibility multiplies rather than adds**, unlike the wildfire engine's
``base`` term. There is no equivalent of "fire arrives from outside": water
goes downhill, so a cell that the hydraulic mosaic puts on high ground does
not flood however hard it rains next door. Below ``susceptibility.floor`` the
engine short-circuits to zero.

**La cascata incendio → alluvione** (#58) entra qui e non dopo il motore: un
suolo percorso dal fuoco è idrofobico, quindi la stessa pioggia scorre invece
di infiltrarsi. È fisica del ramo pluviale, e applicarla come correzione a
punteggio già calcolato lascerebbe `score` e `breakdown` a raccontare due
cose diverse. Il moltiplicatore finisce nel breakdown, così un operatore vede
di quanto e perché.

Amplifica il **solo** ramo pluviale: un incendio a valle non fa crescere un
fiume a monte.

Pure: no DB, no network, no LLM. La suscettibilità viene dal mosaico
idraulico ISPRA già normalizzato per cella, i due segnali dinamici li
recupera il workflow, e i mesi dall'incendio arrivano da FireCheck — che gira
in ogni workflow, quindi la cascata non ha bisogno di uno sweep in più.
"""

from __future__ import annotations

from limen.core.cascades import CascadeRules, load_cascades
from limen.core.cascades.rules import post_fire_flood_multiplier
from limen.core.models.risk import (
    CellFeatureBundle,
    FloodBreakdown,
    RiskScore,
)
from limen.core.scoring.base import classify_score
from limen.core.scoring.flood.trigger import fluvial_trigger, pluvial_trigger
from limen.core.scoring.regional_thresholds import FloodThresholds


class FloodScoringEngine:
    """``ScoringEngine[FloodBreakdown]`` — the V1 baseline for flood."""

    def __init__(
        self, thresholds: FloodThresholds, *, cascades: CascadeRules | None = None
    ) -> None:
        self._t = thresholds
        # Caricate qui e non a ogni cella: sono configurazione, non stato.
        self._cascades = cascades if cascades is not None else load_cascades()

    @property
    def model_version(self) -> str:
        return self._t.model_version

    def score(self, bundle: CellFeatureBundle) -> RiskScore[FloodBreakdown]:
        t = self._t
        static = bundle.static
        dyn = bundle.dynamic

        # An unmapped cell is not a safe cell: the mosaic covers the basins
        # that were officially studied, and "not studied" is not "not
        # floodable". It gets a low floor rather than a zero.
        susceptibility = (
            t.susceptibility.unmapped
            if static.flood_hazard_norm is None
            else static.flood_hazard_norm
        )

        pluvial = pluvial_trigger(
            dyn.flood_forecast_rain_72h_mm,
            soil_moisture=dyn.soil_moisture_0_7,
            imperviousness=static.imperviousness_norm,
            pluvial=t.pluvial,
            imperviousness_cfg=t.imperviousness,
        )
        # Cascata incendio → alluvione, sul solo ramo pluviale.
        post_fire = post_fire_flood_multiplier(
            dyn.months_since_fire, rule=self._cascades.post_fire_flood
        )
        pluvial = min(pluvial * post_fire, 1.0)

        fluvial = fluvial_trigger(dyn.river_discharge_ratio, fluvial=t.fluvial)

        dry_land = susceptibility < t.susceptibility.floor
        score = 0.0 if dry_land else min(susceptibility * max(pluvial, fluvial), 1.0)

        return RiskScore[FloodBreakdown](
            score=score,
            level=classify_score(score, t.classes),
            breakdown=FloodBreakdown(
                susceptibility=susceptibility,
                pluvial=pluvial,
                fluvial=fluvial,
                mapped=static.flood_hazard_norm is not None,
                discharge_ratio=dyn.river_discharge_ratio,
                rain_mm=dyn.flood_forecast_rain_72h_mm,
                post_fire_multiplier=post_fire,
                months_since_fire=dyn.months_since_fire,
            ),
            model_version=t.model_version,
        )


__all__ = ["FloodScoringEngine"]
