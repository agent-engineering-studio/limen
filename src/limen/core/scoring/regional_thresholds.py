"""Regional thresholds loader.

Loads ``regional_thresholds.yaml`` and validates it with a strict
Pydantic v2 schema. The YAML is the single source of truth for every
numeric knob in the deterministic engine — there are no hard-coded
constants in the scoring code.

The file ships packaged at
``limen.config.regional_thresholds.yaml``; the loader resolves it via
:mod:`importlib.resources` so it works in any installation layout
(editable, wheel, container). An explicit override path may be passed
for tests or environment-specific calibrations.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_THRESHOLDS_PACKAGE = "limen.config"
DEFAULT_THRESHOLDS_FILE = "regional_thresholds.yaml"


def _default_thresholds_path() -> Path:
    """Resolve the packaged YAML to a filesystem path."""
    ref = resources.files(DEFAULT_THRESHOLDS_PACKAGE).joinpath(DEFAULT_THRESHOLDS_FILE)
    return Path(str(ref))


DEFAULT_THRESHOLDS_PATH = _default_thresholds_path()


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


class RegionalThresholds(_StrictModel):
    """Top-level config object — strict validation, immutable."""

    model_version: str = Field(..., min_length=1)
    weights: TopWeights
    static: StaticBlock
    meteo: MeteoBlock
    caine: CaineBlock
    api: ApiBlock
    soil: SoilBlock
    # Optional: older YAMLs without a `snow` block validate; rain-on-snow
    # amplification simply stays inactive everywhere.
    snow: SnowBlock | None = None
    seismic: SeismicBlock
    post_fire: PostFireBlock
    # V1.5: optional. Older YAMLs without a `kinematic` block still
    # validate; K simply stays inactive everywhere.
    kinematic: KinematicBlock | None = None
    classes: ClassCutoffs
    # Alert-priority knob (not scoring) — older YAMLs without it validate.
    exposure: ExposureBlock = Field(default_factory=lambda: ExposureBlock())
    # Optional presentational block — older YAMLs without it validate.
    pc_alert: PcAlertMapping = Field(default_factory=lambda: PcAlertMapping())
    target_distribution: TargetDistribution
    calibration: CalibrationBlock


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


def load_regional_thresholds(path: Path | str | None = None) -> RegionalThresholds:
    """Load + validate the YAML and return a :class:`RegionalThresholds`.

    ``path`` defaults to the packaged file. Passing an explicit path bypasses
    the cache, so tests can swap configurations without state leakage.
    """
    if path is None:
        return _load_default_cached()
    raw_path = Path(path)
    text = raw_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    return RegionalThresholds.model_validate(_coerce_class_ranges(raw))


@lru_cache(maxsize=1)
def _load_default_cached() -> RegionalThresholds:
    text = DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    return RegionalThresholds.model_validate(_coerce_class_ranges(raw))
