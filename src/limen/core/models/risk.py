"""Risk-domain DTOs.

These are the *only* types the deterministic engine reads from and
writes to. They are intentionally side-effect-free Pydantic v2 models
so:

* the engine stays a pure function of its inputs;
* assembling the bundle (DB queries, Open-Meteo / INGV / EFFIS fetches)
  is a separate concern that can be tested independently in Phase 4;
* the V2 ML engine can be a drop-in by consuming the same
  ``CellFeatureBundle``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskLevel(StrEnum):
    """Five-class classification used by the V1 engine.

    Member names follow the project spec: ``None_`` (Python's ``None``
    is a reserved keyword, so a trailing underscore), ``Low``,
    ``Moderate``, ``High``, ``VeryHigh``. Values are the human-readable
    forms used in API responses and JSON dumps.
    """

    None_ = "None"
    Low = "Low"
    Moderate = "Moderate"
    High = "High"
    VeryHigh = "VeryHigh"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
class StaticFactors(_Frozen):
    """Per-cell static factors (mirror of ``cell_static_factors`` columns).

    Every field is optional: when the underlying source isn't yet
    populated (DEM / CORINE / lithology pipelines land later), the
    engine must degrade — not crash.
    """

    cell_id: str
    susc_ispra: float | None = Field(default=None, ge=0.0, le=1.0)
    iffi_density_500: float | None = Field(default=None, ge=0.0)
    distance_to_iffi_m: float | None = Field(default=None, ge=0.0)
    slope_deg: float | None = Field(default=None, ge=0.0, le=90.0)
    aspect_deg: float | None = Field(default=None, ge=0.0, le=360.0)
    elevation_m: float | None = None
    twi: float | None = None
    curvature: float | None = None
    lithology: str | None = None
    litho_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    landuse_code: str | None = None
    pai_class_norm: float | None = Field(default=None, ge=0.0, le=1.0)


class RainfallSample(_Frozen):
    """One hourly rainfall observation (mm)."""

    timestamp: datetime
    precipitation_mm: float = Field(..., ge=0.0)


class RainfallSeries(_Frozen):
    """Hourly precipitation time-series used by Caine + API computations."""

    samples: tuple[RainfallSample, ...] = ()

    @property
    def total_mm(self) -> float:
        return float(sum(s.precipitation_mm for s in self.samples))


class SeismicHistoryEvent(_Frozen):
    """One past seismic event relevant to a cell (within the lookback window)."""

    event_id: str
    origin_time: datetime
    magnitude: float = Field(..., gt=0.0)
    distance_km: float = Field(..., ge=0.0)
    pga_g: float = Field(..., ge=0.0, description="Local PGA in units of g")


class DynamicInputs(_Frozen):
    """Time-varying inputs needed by M / E / F components."""

    valuation_time: datetime
    rainfall: RainfallSeries = RainfallSeries()
    api_30_mm: float | None = Field(default=None, ge=0.0)
    api_baseline_mm: float | None = Field(default=None, ge=0.0)
    soil_moisture_0_7: float | None = Field(default=None, ge=0.0, le=1.0)
    seismic_history: tuple[SeismicHistoryEvent, ...] = ()
    months_since_fire: float | None = Field(default=None, ge=0.0)


class CellFeatureBundle(_Frozen):
    """Engine input — everything needed to score one cell at one moment."""

    aoi_id: str
    cell_id: str
    static: StaticFactors
    dynamic: DynamicInputs
    macroregion: str = "italy_default"

    @model_validator(mode="after")
    def _cell_id_consistency(self) -> CellFeatureBundle:
        if self.static.cell_id != self.cell_id:
            raise ValueError(
                f"CellFeatureBundle.cell_id ({self.cell_id!r}) "
                f"differs from static.cell_id ({self.static.cell_id!r})"
            )
        return self


# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
class StaticBreakdown(_Frozen):
    susc_ispra: float = Field(..., ge=0.0, le=1.0)
    iffi_density: float = Field(..., ge=0.0, le=1.0)
    slope: float = Field(..., ge=0.0, le=1.0)
    pai: float = Field(..., ge=0.0, le=1.0)
    litho_weight: float = Field(..., ge=0.0, le=1.0)


class MeteoBreakdown(_Frozen):
    caine_excess: float = Field(..., ge=0.0)
    caine_norm: float = Field(..., ge=0.0, le=1.0)
    api_factor: float = Field(..., ge=0.0, le=1.0)
    soil_factor: float = Field(..., ge=0.0, le=1.0)


class ComponentBreakdown(_Frozen):
    """All five components + their normalised inputs, for auditability.

    Sub-terms are the value of each normalised input *before* weighting:
    a geologist can recombine them with alternative weights if needed.
    """

    s: float = Field(..., ge=0.0, le=1.0)
    m: float = Field(..., ge=0.0, le=1.0)
    e: float = Field(..., ge=0.0, le=1.0)
    f: float = Field(..., ge=0.0, le=1.0)
    h: float = Field(..., ge=0.0, le=1.0)

    static_terms: StaticBreakdown
    meteo_terms: MeteoBreakdown


class RiskScore(_Frozen):
    """Engine output."""

    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    breakdown: ComponentBreakdown
    model_version: str

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


__all__: Sequence[str] = (
    "CellFeatureBundle",
    "ComponentBreakdown",
    "DynamicInputs",
    "MeteoBreakdown",
    "RainfallSample",
    "RainfallSeries",
    "RiskLevel",
    "RiskScore",
    "SeismicHistoryEvent",
    "StaticBreakdown",
    "StaticFactors",
)
