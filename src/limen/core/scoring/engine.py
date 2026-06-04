"""MultiFactorScoringEngine — the V1 deterministic risk engine.

Pure function from :class:`CellFeatureBundle` to :class:`RiskScore`.
No I/O. No LLM. No network. The bundle assembler — fed by the DB, the
caches, and the integration clients — is a separate concern (Phase 4).

The aggregation is the §2.4 weighted linear combination:

    S(c) = w_susc · norm(susc_ISPRA) + w_iffi · norm(iffi_density)
         + w_slope · norm(slope) + w_pai · norm(PAI) + w_litho · litho_weight
    M(c,t) = w_caine · norm(caine_excess) + w_api · api_factor
           + w_soil · soil_factor
    risk = w_S · S + w_M · M + w_E · E + w_F · F + w_H · H

with five-class classification using the cutoffs in
:class:`ClassCutoffs`. ``H = 0`` in V1 (hydrology component arrives in
V1.5+).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from limen.core.models.risk import (
    CellFeatureBundle,
    ComponentBreakdown,
    KinematicBreakdown,
    MeteoBreakdown,
    RiskLevel,
    RiskScore,
    StaticBreakdown,
)
from limen.core.scoring.api import api_factor
from limen.core.scoring.caine import compute_caine
from limen.core.scoring.kinematic import compute_kinematic
from limen.core.scoring.post_fire import post_fire_factor
from limen.core.scoring.regional_thresholds import (
    ClassCutoffs,
    RegionalThresholds,
    SoilBlock,
    load_regional_thresholds,
)
from limen.core.scoring.seismic_decay import compute_seismic

# How much "log10-excess above Caine threshold" should map to 1.0?
# One full decade above threshold is already extreme — we cap norm() at
# that point. Lives here (and not in the YAML) because it is internal
# normalisation, not a tunable knob; the §2.4 paper allows ≥ 1 here.
_CAINE_LOG_EXCESS_CAP = 1.0


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _norm_slope(slope_deg: float | None, saturation_deg: float) -> float:
    if slope_deg is None or saturation_deg <= 0:
        return 0.0
    return _clamp01(slope_deg / saturation_deg)


def _norm_iffi_density(density: float | None) -> float:
    """``iffi_density_500`` saturates at ~3 features per 500 m buffer.

    The figure is empirical (Italian Apennines pilot); calibration may
    refine it via per-AOI ``norm_stats``. For pure-engine use without
    calibration, this default keeps results sensible.
    """
    if density is None or density <= 0:
        return 0.0
    return _clamp01(density / 3.0)


def _norm_caine(excess: float) -> float:
    return _clamp01(excess / _CAINE_LOG_EXCESS_CAP)


def _soil_sigmoid(value: float | None, *, soil: SoilBlock) -> float:
    if value is None:
        return 0.5
    z = soil.sigmoid_steepness * (value - soil.sigmoid_center)
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _classify(score: float, cutoffs: ClassCutoffs) -> RiskLevel:
    if score < cutoffs.low.lo:
        return RiskLevel.None_
    if score < cutoffs.moderate.lo:
        return RiskLevel.Low
    if score < cutoffs.high.lo:
        return RiskLevel.Moderate
    if score < cutoffs.very_high.lo:
        return RiskLevel.High
    return RiskLevel.VeryHigh


@dataclass(frozen=True, slots=True)
class _StaticAggregate:
    s: float
    breakdown: StaticBreakdown


@dataclass(frozen=True, slots=True)
class _MeteoAggregate:
    m: float
    breakdown: MeteoBreakdown


class MultiFactorScoringEngine:
    """Stateless engine bound to a :class:`RegionalThresholds`."""

    def __init__(self, thresholds: RegionalThresholds | None = None) -> None:
        self._t: RegionalThresholds = thresholds or load_regional_thresholds()

    # ------------------------------------------------------------------
    # Static component
    # ------------------------------------------------------------------
    def _static(self, bundle: CellFeatureBundle) -> _StaticAggregate:
        w = self._t.static.weights
        sat = self._t.static.slope_saturation_deg
        sf = bundle.static

        susc = _clamp01(sf.susc_ispra) if sf.susc_ispra is not None else 0.0
        iffi = _norm_iffi_density(sf.iffi_density_500)
        slope = _norm_slope(sf.slope_deg, sat)
        pai = _clamp01(sf.pai_class_norm) if sf.pai_class_norm is not None else 0.0
        litho = _clamp01(sf.litho_weight) if sf.litho_weight is not None else 0.0

        s = (
            w.susc_ispra * susc
            + w.iffi_density * iffi
            + w.slope * slope
            + w.pai * pai
            + w.litho_weight * litho
        )
        return _StaticAggregate(
            s=_clamp01(s),
            breakdown=StaticBreakdown(
                susc_ispra=susc, iffi_density=iffi, slope=slope, pai=pai, litho_weight=litho
            ),
        )

    # ------------------------------------------------------------------
    # Meteo component
    # ------------------------------------------------------------------
    def _meteo(self, bundle: CellFeatureBundle) -> _MeteoAggregate:
        w = self._t.meteo.weights
        caine_excess_val, _event = compute_caine(
            bundle.dynamic.rainfall,
            caine=self._t.caine,
            macroregion=bundle.macroregion,
        )
        caine_norm = _norm_caine(caine_excess_val)

        api_f = api_factor(
            bundle.dynamic.api_30_mm,
            api=self._t.api,
            baseline_mm=bundle.dynamic.api_baseline_mm,
        )
        soil_f = _soil_sigmoid(bundle.dynamic.soil_moisture_0_7, soil=self._t.soil)

        # V1.5 — measured-over-modeled override (§2.9). When the cell
        # carries in-situ readings, they replace the Open-Meteo / soil
        # estimates for the duration of this scoring call. The list of
        # overridden inputs is recorded on the breakdown for auditability.
        overrides: list[str] = []
        sensor = bundle.dynamic.sensor_features
        if sensor is not None:
            if sensor.rainfall_mm is not None:
                caine_norm = _clamp01(
                    sensor.rainfall_mm / max(self._t.caine.event_reconstruction.min_event_mm, 1e-6)
                )
                overrides.append("caine")
            if sensor.pore_pressure_kpa is not None:
                # Treat pore pressure as a direct API proxy normalised by
                # the YAML's sigma so behaviour matches the modeled path.
                api_f = _clamp01(sensor.pore_pressure_kpa / self._t.api.sigmoid_sigma_mm)
                overrides.append("api")
            if sensor.soil_moisture is not None:
                soil_f = _soil_sigmoid(sensor.soil_moisture, soil=self._t.soil)
                overrides.append("soil")

        m = w.caine * caine_norm + w.api * api_f + w.soil * soil_f
        return _MeteoAggregate(
            m=_clamp01(m),
            breakdown=MeteoBreakdown(
                caine_excess=caine_excess_val,
                caine_norm=caine_norm,
                api_factor=api_f,
                soil_factor=soil_f,
                measured_overrides=tuple(overrides),
            ),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def score(self, bundle: CellFeatureBundle) -> RiskScore:
        """Score one cell at one moment. Pure, deterministic.

        V1.5: when the bundle carries a :class:`SensorFeatures` *and*
        a YAML kinematic block is configured, K is computed and the
        top-level weights are renormalised so ``w_K + (scaled S/M/E/F/H)
        = 1``. With no sensor features (or no YAML block), the score is
        byte-for-byte identical to V1.
        """
        static = self._static(bundle)
        meteo = self._meteo(bundle)
        _pga, e = compute_seismic(
            bundle.dynamic.seismic_history,
            as_of=bundle.dynamic.valuation_time,
            seismic=self._t.seismic,
        )
        f = post_fire_factor(bundle.dynamic.months_since_fire, post_fire=self._t.post_fire)
        # H is always 0 in V1 (hydrology component lands V1.5+).
        h = 0.0

        k_value, k_breakdown = compute_kinematic(
            bundle.dynamic.sensor_features,
            kinematic=self._t.kinematic,
        )

        w = self._t.weights
        kinematic_block = self._t.kinematic
        monitored = (
            kinematic_block is not None
            and bundle.dynamic.sensor_features is not None
            and bundle.dynamic.sensor_features.has_kinematic_signal
        )
        if monitored and kinematic_block is not None:
            w_k = kinematic_block.weights.k
            remaining = 1.0 - w_k
            total = w_k * k_value + remaining * (
                w.static * static.s
                + w.meteo * meteo.m
                + w.seismic * e
                + w.fire * f
                + w.hydrology * h
            )
        else:
            # Pure V1 path — K is zero, weights untouched.
            k_breakdown = (
                k_breakdown if bundle.dynamic.sensor_features is not None else KinematicBreakdown()
            )
            total = (
                w.static * static.s
                + w.meteo * meteo.m
                + w.seismic * e
                + w.fire * f
                + w.hydrology * h
            )
        score_val = _clamp01(total)

        return RiskScore(
            score=score_val,
            level=_classify(score_val, self._t.classes),
            breakdown=ComponentBreakdown(
                s=static.s,
                m=meteo.m,
                e=e,
                f=f,
                h=h,
                k=k_value if monitored else 0.0,
                static_terms=static.breakdown,
                meteo_terms=meteo.breakdown,
                kinematic_terms=k_breakdown if monitored else None,
            ),
            model_version=self._t.model_version,
            monitored=monitored,
            hard_escalation=k_breakdown.hard_escalation if monitored else False,
        )


def score(
    bundle: CellFeatureBundle,
    *,
    thresholds: RegionalThresholds | None = None,
) -> RiskScore:
    """Functional convenience wrapper around :class:`MultiFactorScoringEngine`."""
    return MultiFactorScoringEngine(thresholds).score(bundle)
