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
from typing import Any

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
    s_vs_ispra_correlation_min: float = Field(..., ge=0.0, le=1.0)
    backtest: BacktestTargets


class RegionalThresholds(_StrictModel):
    """Top-level config object — strict validation, immutable."""

    model_version: str = Field(..., min_length=1)
    weights: TopWeights
    static: StaticBlock
    meteo: MeteoBlock
    caine: CaineBlock
    api: ApiBlock
    soil: SoilBlock
    seismic: SeismicBlock
    post_fire: PostFireBlock
    classes: ClassCutoffs
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
