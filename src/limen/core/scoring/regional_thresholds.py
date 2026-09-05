"""Per-hazard thresholds loader.

Loads one hazard's YAML and validates it with a strict Pydantic v2 schema.
The YAML is the single source of truth for every numeric knob in the
deterministic engine — there are no hard-coded constants in the scoring code.

Files ship packaged at ``limen/config/hazards/<hazard>.yaml``, one per hazard
named after the enum value, and the loader resolves them via
:mod:`importlib.resources` so it works in any installation layout (editable,
wheel, container). An explicit override path may be passed for tests or
environment-specific calibrations.

Each hazard has its **own schema**, selected by :data:`SCHEMA_BY_HAZARD`.
:class:`HazardThresholds` holds only what every danger has -- a version, five
class cutoffs, a civil-protection mapping and the alert-priority knob;
:class:`RegionalThresholds` adds the landslide blocks (S/M/E/F/H/K, Caine,
seismic decay, post-fire) and :class:`WildfireThresholds` the FWI ones. They
share no scoring block because they share no physics: a Caine rainfall
threshold means nothing to a fire, and a drought code means nothing to a
slope.

A surface that must work for any hazard -- the legend, the alert priority --
types against the base and asks for :meth:`HazardThresholds.model_card`
rather than reaching for blocks only one hazard has.
"""

from __future__ import annotations

from functools import cache
from importlib import resources
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType

DEFAULT_THRESHOLDS_PACKAGE = "limen.config"
#: One file per hazard, named after the enum value: adding a hazard is a new
#: YAML plus a registry entry, never a code change here. There is deliberately
#: no shared-blocks file: `classes`, `exposure`, `pc_alert`,
#: `target_distribution` and `calibration` are per-hazard in substance -- each
#: danger has its own class cutoffs and its own civil-protection mapping -- so
#: duplicating them in `flood.yaml` beats a merge layer nobody can debug.
HAZARD_THRESHOLDS_DIR = "hazards"


def hazard_thresholds_path(hazard: HazardType) -> Path:
    """Resolve a hazard's packaged YAML to a filesystem path."""
    ref = (
        resources.files(DEFAULT_THRESHOLDS_PACKAGE)
        .joinpath(HAZARD_THRESHOLDS_DIR)
        .joinpath(f"{hazard.value}.yaml")
    )
    return Path(str(ref))


DEFAULT_THRESHOLDS_PATH = hazard_thresholds_path(DEFAULT_HAZARD)


# ---------------------------------------------------------------------------
# Schema models — all values come from the YAML, validated on load.
# ---------------------------------------------------------------------------
class _StrictModel(BaseModel):
    """Pydantic base with strict mode and forbidden extras."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_assignment=True,
    )


class TopWeights(_StrictModel):
    """Top-level component weights (must sum to 1 — V1.5 will relax this)."""

    static: float = Field(..., ge=0.0, le=1.0)
    meteo: float = Field(..., ge=0.0, le=1.0)
    seismic: float = Field(..., ge=0.0, le=1.0)
    fire: float = Field(..., ge=0.0, le=1.0)
    hydrology: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> TopWeights:
        total = self.static + self.meteo + self.seismic + self.fire + self.hydrology
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"weights must sum to 1.0, got {total}")
        return self


class StaticWeights(_StrictModel):
    susc_ispra: float = Field(..., ge=0.0, le=1.0)
    iffi_density: float = Field(..., ge=0.0, le=1.0)
    slope: float = Field(..., ge=0.0, le=1.0)
    pai: float = Field(..., ge=0.0, le=1.0)
    litho_weight: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> StaticWeights:
        total = self.susc_ispra + self.iffi_density + self.slope + self.pai + self.litho_weight
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"static weights must sum to 1.0, got {total}")
        return self


class StaticBlock(_StrictModel):
    weights: StaticWeights
    slope_saturation_deg: float = Field(..., gt=0.0, le=90.0)
    # IFFI-density (features within 500 m of a cell) at which the term
    # saturates to 1.0. Was a hard-coded 3.0 in the engine; moved here and
    # rescaled after the density query fix raised typical counts ~5×.
    iffi_density_saturation: float = Field(..., gt=0.0)


class MeteoWeights(_StrictModel):
    caine: float = Field(..., ge=0.0, le=1.0)
    api: float = Field(..., ge=0.0, le=1.0)
    soil: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> MeteoWeights:
        total = self.caine + self.api + self.soil
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"meteo weights must sum to 1.0, got {total}")
        return self


class MeteoBlock(_StrictModel):
    weights: MeteoWeights


class CaineEventReconstruction(_StrictModel):
    no_rain_break_hours: int = Field(..., gt=0)
    min_event_mm: float = Field(..., gt=0.0)


class CaineMacroregion(_StrictModel):
    alpha: float = Field(..., gt=0.0)
    beta: float = Field(..., gt=0.0)


class CaineBlock(_StrictModel):
    event_reconstruction: CaineEventReconstruction
    macroregions: dict[str, CaineMacroregion]

    @field_validator("macroregions")
    @classmethod
    def _has_default(cls, v: dict[str, CaineMacroregion]) -> dict[str, CaineMacroregion]:
        if "italy_default" not in v:
            raise ValueError("caine.macroregions must define 'italy_default'")
        return v


class RainFloorMacroregion(_StrictModel):
    alpha: float = Field(..., gt=0.0)
    beta: float = Field(..., gt=0.0)


class RainFloorBlock(_StrictModel):
    """Issue #20 — permissive Caine T2 envelope that bypasses the tier.

    A cell whose rainfall crosses this floor *and* whose antecedent wetness
    (soil-moisture sigmoid) is at least ``wetness_min`` must be scored
    regardless of its susceptibility tier — the floor is the correctness
    constraint that guards a national EWS against silent false negatives on
    exceptional rain over low-susceptibility cells.
    """

    wetness_min: float = Field(..., ge=0.0, le=1.0)
    macroregions: dict[str, RainFloorMacroregion]

    @field_validator("macroregions")
    @classmethod
    def _has_default(cls, v: dict[str, RainFloorMacroregion]) -> dict[str, RainFloorMacroregion]:
        if "italy_default" not in v:
            raise ValueError("rain_floor.macroregions must define 'italy_default'")
        return v


class FloodForecastMacroregion(_StrictModel):
    center_mm: float = Field(..., gt=0.0)  # 72h forecast rain at sigmoid centre
    steepness_mm: float = Field(..., gt=0.0)  # sigmoid σ in mm


class FloodForecastBlock(_StrictModel):
    """Issue #8 — dynamic, multi-source flood uplift on the hydrology quota H.

    **NOT the flood hazard.** This block tunes the hydrology component H of
    *landslide* scoring: forecast rain, river discharge and coastal surge
    raise the H term of a landslide score. The flood hazard is a separate
    engine with its own config file (Fase 3, issue #63). Whoever implements it
    will find these names first — do not reuse them.

    Combines three forward-looking signals, each scaled by the ISPRA static
    hydraulic hazard (``flood_hazard_norm``):

    * **pluvial** — forecast 72h rain (Open-Meteo forecast), sigmoid per macroregion;
    * **fluvial** — river-discharge ratio vs seasonal normal (Open-Meteo Flood
      API / GloFAS), sigmoid centred at ``discharge_ratio_center``;
    * **coastal** — sea surge / wave signal in [0,1] (Open-Meteo Marine API).

    ``bonus = hazard_uplift · flood_hazard_norm · max(pluvial, fluvial, coastal)``,
    added to the static hazard. Any missing signal contributes 0, so the score
    is byte-identical to V1 when no flood feed is present.
    """

    hazard_uplift: float = Field(..., ge=0.0, le=5.0)
    discharge_ratio_center: float = Field(..., gt=0.0)  # ratio at sigmoid centre
    discharge_ratio_steepness: float = Field(..., gt=0.0)
    macroregions: dict[str, FloodForecastMacroregion]

    @field_validator("macroregions")
    @classmethod
    def _has_default(
        cls, v: dict[str, FloodForecastMacroregion]
    ) -> dict[str, FloodForecastMacroregion]:
        if "italy_default" not in v:
            raise ValueError("flood_forecast.macroregions must define 'italy_default'")
        return v


class ApiBaseline(_StrictModel):
    fallback_mm: float = Field(..., ge=0.0)


class ApiBlock(_StrictModel):
    horizon_days: int = Field(..., gt=0)
    decay_k: float = Field(..., gt=0.0, lt=1.0)
    sigmoid_sigma_mm: float = Field(..., gt=0.0)
    baseline: ApiBaseline


class SoilBlock(_StrictModel):
    sigmoid_center: float = Field(..., ge=0.0, le=1.0)
    sigmoid_steepness: float = Field(..., gt=0.0)


class SnowBlock(_StrictModel):
    """Rain-on-snow amplification of M (additive, baseline-preserving).

    With a standing snowpack (depth ≥ ``ros_min_depth_m``), rain in the last
    24 h loads the pack and adds melt water: the factor ramps to 1 at
    ``ros_rain_scale_mm`` and adds up to ``weight`` to M. No snow ⇒ factor 0
    ⇒ scores byte-identical to the pre-snow engine.
    """

    ros_min_depth_m: float = Field(..., ge=0.0)
    ros_rain_scale_mm: float = Field(..., gt=0.0)
    weight: float = Field(..., ge=0.0, le=1.0)


class SeismicBlock(_StrictModel):
    tau_days: float = Field(..., gt=0.0)
    min_magnitude: float = Field(..., gt=0.0)
    lookback_days: int = Field(..., gt=0)
    pga_threshold_g: float = Field(..., gt=0.0)
    pga_scale_g: float = Field(..., gt=0.0)


class PostFireBlock(_StrictModel):
    peak_months: float = Field(..., ge=0.0)
    curve_denominator: float = Field(..., gt=0.0)
    window_months_max: float = Field(..., gt=0.0)


class KinematicWeights(_StrictModel):
    """Per-cell weight K takes when monitored (renormalizes the others)."""

    k: float = Field(..., ge=0.0, le=1.0)


class KinematicBlock(_StrictModel):
    """V1.5 K component — displacement velocity / Fukuzono inverse-velocity."""

    v_threshold_mmd: float = Field(..., gt=0.0)
    sigma_v: float = Field(..., gt=0.0)
    acceleration_alarm_mmd2: float = Field(..., gt=0.0)
    inverse_velocity_alarm: float = Field(..., gt=0.0)
    weights: KinematicWeights


class ExposureBlock(_StrictModel):
    """Alert-priority exposure multiplier — NOT a scoring-engine input.

    ``priority = score * (1 + factor)`` with ``factor`` capped at ``cap``.
    Road/rail terms grade by distance from the OSM network; when the OSM
    term contributes nothing (network not ingested, or beyond the bands)
    the CORINE 12x flags act as fallback — they also cover what the
    road/rail extract can't see (industrial 121, ports/airports 123-124).
    """

    urban_here: float = Field(default=1.0, ge=0.0)
    urban_near: float = Field(default=0.5, ge=0.0)
    road_strong_m: float = Field(default=250.0, gt=0.0)
    road_strong: float = Field(default=0.6, ge=0.0)
    road_medium_m: float = Field(default=1000.0, gt=0.0)
    road_medium: float = Field(default=0.3, ge=0.0)
    rail_strong_m: float = Field(default=250.0, gt=0.0)
    rail_strong: float = Field(default=0.5, ge=0.0)
    rail_medium_m: float = Field(default=1000.0, gt=0.0)
    rail_medium: float = Field(default=0.25, ge=0.0)
    infra_here_fallback: float = Field(default=0.6, ge=0.0)
    infra_near_fallback: float = Field(default=0.3, ge=0.0)
    cap: float = Field(default=2.0, gt=0.0)

    @model_validator(mode="after")
    def _bands_ordered(self) -> ExposureBlock:
        if self.road_strong_m > self.road_medium_m:
            raise ValueError("exposure.road_strong_m must be <= road_medium_m")
        if self.rail_strong_m > self.rail_medium_m:
            raise ValueError("exposure.rail_strong_m must be <= rail_medium_m")
        return self


class ClassRange(_StrictModel):
    """Closed-open ``[lo, hi)`` interval; the final class is closed-closed."""

    lo: float
    hi: float


class ClassCutoffs(_StrictModel):
    """Maps the 5 V1 classes to their score ranges."""

    none: ClassRange
    low: ClassRange
    moderate: ClassRange
    high: ClassRange
    very_high: ClassRange

    @model_validator(mode="after")
    def _contiguous_and_covers_unit(self) -> ClassCutoffs:
        ranges = [self.none, self.low, self.moderate, self.high, self.very_high]
        if ranges[0].lo != 0.0 or ranges[-1].hi != 1.0:
            raise ValueError("class cutoffs must cover [0, 1]")
        for prev, nxt in pairwise(ranges):
            if prev.hi != nxt.lo:
                raise ValueError(f"class cutoffs must be contiguous; gap {prev.hi} != {nxt.lo}")
            if prev.lo >= prev.hi:
                raise ValueError(f"class range invalid: lo {prev.lo} >= hi {prev.hi}")
        return self


class TargetDistribution(_StrictModel):
    none: float = Field(..., ge=0.0, le=1.0)
    low: float = Field(..., ge=0.0, le=1.0)
    moderate: float = Field(..., ge=0.0, le=1.0)
    high: float = Field(..., ge=0.0, le=1.0)
    very_high: float = Field(..., ge=0.0, le=1.0)


class BacktestTargets(_StrictModel):
    hit_rate_min: float = Field(..., ge=0.0, le=1.0)
    far_max: float = Field(..., ge=0.0, le=1.0)
    lead_time_hours_min: float = Field(..., ge=0.0)


class CalibrationBlock(_StrictModel):
    # None disables the S↔ISPRA correlation gate (susceptibility is no longer
    # a scoring input once GeoServer is the static-data source).
    s_vs_ispra_correlation_min: float | None = Field(default=None, ge=0.0, le=1.0)
    backtest: BacktestTargets


class PcAlertMapping(_StrictModel):
    """Presentational mapping of the 5 classes onto the Protezione
    Civile alert scale. Labels only — scores and classes never change."""

    none: Literal["verde", "gialla", "arancione", "rossa"] = "verde"
    low: Literal["verde", "gialla", "arancione", "rossa"] = "verde"
    moderate: Literal["verde", "gialla", "arancione", "rossa"] = "gialla"
    high: Literal["verde", "gialla", "arancione", "rossa"] = "arancione"
    very_high: Literal["verde", "gialla", "arancione", "rossa"] = "rossa"

    def for_level(self, level: str) -> str:
        """PC colour for a RiskLevel value ("None", "Low", ...)."""
        key = {"None": "none", "VeryHigh": "very_high"}.get(level, level.lower())
        return str(getattr(self, key, "verde"))


class HazardThresholds(_StrictModel):
    """What every hazard's configuration has, whatever the danger is.

    A score in [0, 1], five classes, a colour for the civil-protection scale,
    and a way to rank which alerts matter more. Everything else is physics,
    and physics is per hazard.
    """

    model_version: str = Field(..., min_length=1)
    classes: ClassCutoffs
    # Alert-priority knob (not scoring) — older YAMLs without it validate.
    exposure: ExposureBlock = Field(default_factory=lambda: ExposureBlock())
    # Optional presentational block — older YAMLs without it validate.
    pc_alert: PcAlertMapping = Field(default_factory=lambda: PcAlertMapping())

    def model_card(self) -> dict[str, Any]:
        """The versioned numbers the public "how it works" page draws.

        Lives here so the API stays free of scoring knowledge: an endpoint
        that reached into ``.weights`` would have to grow a branch per hazard,
        and would break the moment a hazard has no such block.
        """
        return {}


class RegionalThresholds(HazardThresholds):
    """Landslide configuration — strict validation, immutable."""

    weights: TopWeights
    static: StaticBlock
    meteo: MeteoBlock
    caine: CaineBlock
    api: ApiBlock
    soil: SoilBlock
    # Optional (issue #20): older YAMLs without a `rain_floor` block validate;
    # the floor predicate then returns False everywhere (tier bypass inactive).
    rain_floor: RainFloorBlock | None = None
    # Optional (issue #8): dynamic multi-source flood uplift on H. Absent ⇒
    # bonus 0 everywhere (H stays purely static, byte-identical to V1).
    flood_forecast: FloodForecastBlock | None = None
    # Optional: older YAMLs without a `snow` block validate; rain-on-snow
    # amplification simply stays inactive everywhere.
    snow: SnowBlock | None = None
    seismic: SeismicBlock
    post_fire: PostFireBlock
    # V1.5: optional. Older YAMLs without a `kinematic` block still
    # validate; K simply stays inactive everywhere.
    kinematic: KinematicBlock | None = None
    target_distribution: TargetDistribution
    calibration: CalibrationBlock

    def model_card(self) -> dict[str, Any]:
        return {
            "weights": {
                "static": self.weights.static,
                "meteo": self.weights.meteo,
                "seismic": self.weights.seismic,
                "fire": self.weights.fire,
                "hydrology": self.weights.hydrology,
            },
            "meteo_weights": {
                "caine": self.meteo.weights.caine,
                "api": self.meteo.weights.api,
                "soil": self.meteo.weights.soil,
            },
            "caine": {
                "macroregions": {
                    name: {"alpha": mr.alpha, "beta": mr.beta}
                    for name, mr in self.caine.macroregions.items()
                },
            },
            "api": {
                "sigmoid_sigma_mm": self.api.sigmoid_sigma_mm,
                "baseline_fallback_mm": self.api.baseline.fallback_mm,
            },
            "soil": {
                "sigmoid_center": self.soil.sigmoid_center,
                "sigmoid_steepness": self.soil.sigmoid_steepness,
            },
            "seismic": {
                "tau_days": self.seismic.tau_days,
                "pga_threshold_g": self.seismic.pga_threshold_g,
                "pga_scale_g": self.seismic.pga_scale_g,
            },
            "post_fire": {
                "peak_months": self.post_fire.peak_months,
                "curve_denominator": self.post_fire.curve_denominator,
                "window_months_max": self.post_fire.window_months_max,
            },
        }


# ---------------------------------------------------------------------------
# Wildfire (#61)
# ---------------------------------------------------------------------------
class FwiBlock(_StrictModel):
    """Everything the FWI chain needs that a deployment may legitimately set.

    Van Wagner's own coefficients are *not* here: they are the equations, not
    a calibration, and putting them in YAML would invite someone to "tune" a
    published standard. What is here is the starting point of the recursive
    codes and the latitude-dependent day-length tables.
    """

    ffmc_start: float = Field(..., ge=0.0, le=101.0)
    dmc_start: float = Field(..., ge=0.0)
    dc_start: float = Field(..., ge=0.0)
    #: Twelve monthly factors, January first (Van Wagner Table 2, 46°N).
    day_length_dmc: tuple[float, ...]
    #: Twelve monthly factors, January first (Van Wagner Table 3).
    day_length_dc: tuple[float, ...]
    #: FWI value mapped to a normalised 1.0. EFFIS calls ≥ 50 "extreme"; above
    #: it the index keeps climbing but the operational answer stops changing.
    normalisation_max: float = Field(..., gt=0.0)
    #: Days of spin-up below which the codes are not yet meaningful. The
    #: engine still scores, but flags the breakdown so nobody reads a
    #: three-day-old chain as a seasoned one.
    spinup_days: int = Field(..., ge=0)
    #: Longest interruption a chain survives. Beyond it the stored state is a
    #: fiction -- carrying a code across three weeks of missing weather as if
    #: the days were consecutive is worse than restarting from the seed and
    #: saying so. Well under the DC's ~52-day memory, so a short outage still
    #: keeps the drought signal it took weeks to build.
    max_gap_days: int = Field(..., ge=1)
    #: Weather-node grid step, in degrees. It is the key of `fwi_state`, so
    #: changing it starts fresh chains and restarts the spin-up: a
    #: configuration decision, not a per-run knob.
    node_spacing_deg: float = Field(..., gt=0.0, le=5.0)

    # YAML has no tuple, and the schema is in strict mode: coerce before
    # validation so the parsed table stays immutable like every other block.
    @field_validator("day_length_dmc", "day_length_dc", mode="before")
    @classmethod
    def _twelve_months(cls, v: object) -> object:
        if isinstance(v, list):
            v = tuple(v)
        if isinstance(v, tuple) and len(v) != 12:
            raise ValueError(f"day-length tables need 12 monthly entries, got {len(v)}")
        return v


class FuelBlock(_StrictModel):
    """CORINE Land Cover class → flammability in [0, 1].

    Keyed by CLC code prefix, longest match wins, so ``312`` (coniferous
    forest) can differ from the ``31`` it lives under. A cell whose land cover
    is unknown gets ``default``, not zero: absent data must not read as
    "cannot burn".
    """

    default: float = Field(..., ge=0.0, le=1.0)
    by_clc_prefix: dict[str, float] = Field(default_factory=dict)

    @field_validator("by_clc_prefix")
    @classmethod
    def _in_unit_interval(cls, v: dict[str, float]) -> dict[str, float]:
        for code, value in v.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"fuel.by_clc_prefix[{code}] must be in [0, 1], got {value}")
        return v

    def for_code(self, landuse_code: str | None) -> float:
        """Flammability for a CLC code, longest prefix wins."""
        if not landuse_code:
            return self.default
        matches = [p for p in self.by_clc_prefix if landuse_code.startswith(p)]
        if not matches:
            return self.default
        return self.by_clc_prefix[max(matches, key=len)]


class WildfireWeights(_StrictModel):
    """How the terrain modulates the weather. Must sum to 1.

    These weight the *terrain* factor that multiplies the FWI term, so a cell
    with the maximum of every one of them scores exactly its normalised FWI.
    That is what keeps the class cutoffs readable as EFFIS danger bands.
    """

    #: Weight given to nothing in particular -- the share of the danger a cell
    #: carries because fire arrives from outside it. It is why bare rock in
    #: extreme fire weather is not zero.
    base: float = Field(..., ge=0.0, le=1.0)
    fuel: float = Field(..., ge=0.0, le=1.0)
    slope: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> WildfireWeights:
        total = self.base + self.fuel + self.slope
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"wildfire weights must sum to 1, got {total}")
        return self


class SlopeBlock(_StrictModel):
    """Slope amplification: fire climbs, so steepness raises the rate of spread."""

    #: Degrees mapped to a normalised 1.0. Above ~35° Mediterranean slopes are
    #: rock more often than fuel, so the curve saturating there is physical.
    saturation_deg: float = Field(..., gt=0.0, le=90.0)


class WildfireThresholds(HazardThresholds):
    """Wildfire configuration (#61).

    Shares nothing with the landslide schema beyond the base: the score is
    ``FWI × fuel × slope``, not S/M/E/F/H, so a common block would be a
    coincidence of names rather than of meaning.
    """

    weights: WildfireWeights
    fwi: FwiBlock
    fuel: FuelBlock
    slope: SlopeBlock
    calibration: CalibrationBlock | None = None

    def model_card(self) -> dict[str, Any]:
        return {
            "weights": {
                "base": self.weights.base,
                "fuel": self.weights.fuel,
                "slope": self.weights.slope,
            },
            "fwi": {
                "normalisation_max": self.fwi.normalisation_max,
                "spinup_days": self.fwi.spinup_days,
            },
            "slope": {"saturation_deg": self.slope.saturation_deg},
        }


#: Which schema validates which hazard's YAML. Adding a hazard is an entry
#: here plus the file -- the loader has no branch of its own.
SCHEMA_BY_HAZARD: dict[HazardType, type[HazardThresholds]] = {
    HazardType.LANDSLIDE: RegionalThresholds,
    HazardType.WILDFIRE: WildfireThresholds,
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _coerce_class_ranges(raw: dict[str, Any]) -> dict[str, Any]:
    """The YAML stores class ranges as ``[lo, hi]`` pairs; Pydantic wants dicts."""
    out = dict(raw)
    classes = dict(out.get("classes") or {})
    for name, value in list(classes.items()):
        if isinstance(value, list | tuple) and len(value) == 2:
            classes[name] = {"lo": float(value[0]), "hi": float(value[1])}
    out["classes"] = classes
    return out


def _schema_for(hazard: HazardType) -> type[HazardThresholds]:
    try:
        return SCHEMA_BY_HAZARD[hazard]
    except KeyError:
        raise FileNotFoundError(
            f"no thresholds schema registered for hazard {hazard.value!r}"
        ) from None


def load_hazard_thresholds(
    hazard: HazardType = DEFAULT_HAZARD, path: Path | str | None = None
) -> HazardThresholds:
    """Load + validate one hazard's YAML with that hazard's own schema.

    ``path`` defaults to the packaged file for ``hazard``. Passing an explicit
    path bypasses the cache, so tests can swap configurations without state
    leakage.

    Returns the **base** type. A caller that needs landslide blocks calls
    :func:`load_regional_thresholds`, which is typed for them: widening the
    return here and narrowing at each site would push an ``isinstance`` into
    every consumer for no gain.
    """
    if path is None:
        return _load_cached(hazard)
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return _schema_for(hazard).model_validate(_coerce_class_ranges(raw))


def load_regional_thresholds(path: Path | str | None = None) -> RegionalThresholds:
    """Landslide thresholds, typed for the landslide engine."""
    loaded = load_hazard_thresholds(DEFAULT_HAZARD, path)
    if not isinstance(loaded, RegionalThresholds):
        raise TypeError(
            f"landslide YAML validated as {type(loaded).__name__}; "
            "SCHEMA_BY_HAZARD is misconfigured"
        )
    return loaded


# Cached per hazard, not globally: two hazards must never share a parsed
# config, and `maxsize=None` is bounded by the enum.
@cache
def _load_cached(hazard: HazardType) -> HazardThresholds:
    text = hazard_thresholds_path(hazard).read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    return _schema_for(hazard).model_validate(_coerce_class_ranges(raw))
