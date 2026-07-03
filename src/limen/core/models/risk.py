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

from limen.core.models.sensor import SensorFeatures


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
    # Phase 12+ — ISPRA Mosaicatura Idraulica, mapped onto the same
    # AA/P1..P4 ladder as PAI. NULL = unknown; the engine treats unknown
    # as H = 0 (V1 baseline behaviour).
    flood_hazard_norm: float | None = Field(default=None, ge=0.0, le=1.0)


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
    # Standing snowpack depth over the window (m) — drives the rain-on-snow
    # amplification of M. AOI-level in V1 (like soil moisture).
    snow_depth_m: float | None = Field(default=None, ge=0.0)
    seismic_history: tuple[SeismicHistoryEvent, ...] = ()
    months_since_fire: float | None = Field(default=None, ge=0.0)
    # V1.5 — per-cell in-situ aggregate. Absent on cells without sensors;
    # the engine then runs the pure V1 path for that cell.
    sensor_features: SensorFeatures | None = None


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
    # Rain-on-snow amplification (0 when no snowpack / no snow block).
    snow_factor: float = Field(default=0.0, ge=0.0, le=1.0)
    # V1.5: which inputs came from in-situ sensors (vs Open-Meteo).
    # Empty tuple on the pure V1 path.
    measured_overrides: tuple[str, ...] = ()


class KinematicBreakdown(_Frozen):
    """Sub-terms for the V1.5 K component (zero when no sensor coverage)."""

    velocity_mmd: float | None = None
    acceleration_mmd2: float | None = None
    inverse_velocity: float | None = None
    velocity_score: float = Field(default=0.0, ge=0.0, le=1.0)
    acceleration_score: float = Field(default=0.0, ge=0.0, le=1.0)
    hard_escalation: bool = False


class ComponentBreakdown(_Frozen):
    """All components + their normalised inputs, for auditability.

    V1 ships five components (S/M/E/F/H, ``k`` always 0). V1.5 activates
    K on monitored cells and renormalises the others — but the same DTO
    shape carries both regimes so downstream consumers (ChatAgents,
    persistence, frontend) stay backwards-compatible.
    """

    s: float = Field(..., ge=0.0, le=1.0)
    m: float = Field(..., ge=0.0, le=1.0)
    e: float = Field(..., ge=0.0, le=1.0)
    f: float = Field(..., ge=0.0, le=1.0)
    h: float = Field(..., ge=0.0, le=1.0)
    k: float = Field(default=0.0, ge=0.0, le=1.0)

    static_terms: StaticBreakdown
    meteo_terms: MeteoBreakdown
    kinematic_terms: KinematicBreakdown | None = None


class RiskScore(_Frozen):
    """Engine output."""

    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    breakdown: ComponentBreakdown
    model_version: str
    # V1.5 — operator-facing hint that the engine took the in-situ path
    # for this cell (raised confidence + the M' override + K active).
    monitored: bool = False
    # V1.5 — set by the engine when acceleration ≥ alarm. The
    # AlertDispatch executor uses this to bypass the threshold gate.
    hard_escalation: bool = False

    def to_dict(self) -> dict[str, object]:
        return self.model_dump(mode="json")


__all__: Sequence[str] = (
    "CellFeatureBundle",
    "ComponentBreakdown",
    "DynamicInputs",
    "KinematicBreakdown",
    "MeteoBreakdown",
    "RainfallSample",
    "RainfallSeries",
    "RiskLevel",
    "RiskScore",
    "SeismicHistoryEvent",
    "SensorFeatures",
    "StaticBreakdown",
    "StaticFactors",
)
