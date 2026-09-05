"""Workflow state container.

Flows through every :class:`Executor` in the sequential pipeline. Each
node copies the context with the snapshots it produced; the final node
(``PersistResult``) writes the assembled :class:`RiskAssessment` back to
the DB.

Pydantic v2 with ``frozen=False`` is intentional — the workflow is
explicitly stateful — but every executor uses
:meth:`pydantic.BaseModel.model_copy` to return a fresh instance, so
state mutations stay explicit.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import (
    AnyHazardBreakdown,
    FireWeatherState,
    RiskLevel,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.core.models.sensor import SensorFeatures


class CellRiskRecord(BaseModel):
    """One per-cell scoring result inside the assessment."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    hazard_type: HazardType = DEFAULT_HAZARD
    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    #: The hazard's own breakdown, typed. Before Fase 2 this record carried
    #: the landslide components flattened onto itself, which is why every
    #: consumer of a scored cell had to be a landslide consumer. They now ask
    #: the breakdown for what they need (`components`, `factors_payload`,
    #: `predisposition`), and adding a hazard touches none of them.
    breakdown: AnyHazardBreakdown
    monitored: bool = False
    hard_escalation: bool = False

    @property
    def predisposition(self) -> float:
        """Static susceptibility, whatever carries it for this hazard."""
        return self.breakdown.predisposition()


class RiskAnalysisDTO(BaseModel):
    """Pydantic mirror of the RiskAnalyst structured output."""

    model_config = ConfigDict(extra="forbid")

    driver: str
    anomalies: list[str] = Field(default_factory=list)
    attention_window_hours: int
    confidence: float = Field(..., ge=0.0, le=1.0)


class AggregateAssessment(BaseModel):
    """AOI-level summary attached to the persisted ``risk_assessments`` row."""

    model_config = ConfigDict(extra="forbid")

    aoi_id: str
    hazard_type: HazardType = DEFAULT_HAZARD
    horizon: str = "24h"
    pipeline_version: str = "v1-deterministic"
    model_version: str
    valuation_time: datetime
    n_cells: int = 0
    cells_high_or_above: int = 0
    cells_by_level: dict[str, int] = Field(default_factory=dict)
    top_cells: list[CellRiskRecord] = Field(default_factory=list)
    analysis: RiskAnalysisDTO | None = None
    briefing_it: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class MonitoringContext(BaseModel):
    """Carries everything the workflow learns about a single run."""

    model_config = ConfigDict(extra="forbid")

    aoi_id: str
    hazard_type: HazardType = DEFAULT_HAZARD
    valuation_time: datetime
    enable_insitu: bool = False

    # Geometry slice — set by AreaResolver
    bbox: tuple[float, float, float, float] | None = None
    cell_ids: Sequence[str] = Field(default_factory=tuple)
    # (lon, lat) centroid per cell — lets the assembler map each cell to its
    # nearest rainfall node instead of one AOI-wide series.
    cell_centroids: dict[str, tuple[float, float]] = Field(default_factory=dict)

    # Snapshots filled progressively
    static_by_cell: dict[str, StaticFactors] = Field(default_factory=dict)
    meteo_centroid_lonlat: tuple[float, float] | None = None
    meteo_samples: Sequence[Any] = Field(default_factory=tuple)
    # Per-node rainfall grid (MeteoFetch, when enabled): sampling nodes over
    # the bbox + one hourly series per node. Empty ⇒ the assembler falls back
    # to the single AOI-centroid `meteo_samples` series.
    rain_nodes: Sequence[tuple[float, float]] = Field(default_factory=tuple)
    rainfall_by_node: Sequence[Any] = Field(default_factory=tuple)
    api_30_mm: float | None = None
    soil_moisture_0_7: float | None = None
    # Max standing snowpack over the window (m) — rain-on-snow input.
    snow_depth_m: float | None = None
    # Issue #8 — AOI-level dynamic flood signals (opt-in feed). The assembler
    # copies them onto each cell's DynamicInputs; None ⇒ flood bonus 0.
    flood_forecast_rain_72h_mm: float | None = None
    river_discharge_ratio: float | None = None
    coastal_surge_norm: float | None = None
    # Fase 2 (#62) — la catena FWI del giorno, per nodo del reticolo globale.
    # Popolata dallo step FwiUpdate solo nel workflow incendio; l'assembler dà
    # a ogni cella la catena del nodo più vicino. `None` in una posizione =
    # nessuna catena per quel nodo, che il motore dichiara invece di
    # sostituire con uno zero.
    fwi_nodes: Sequence[tuple[float, float]] = Field(default_factory=tuple)
    fwi_by_node: Sequence[FireWeatherState | None] = Field(default_factory=tuple)
    seismic_events: Sequence[SeismicHistoryEvent] = Field(default_factory=tuple)
    months_since_fire: float | None = None
    sensor_payload: dict[str, Any] | None = None
    # V1.5 — populated by SensorFetchExecutor when enable_insitu=True.
    sensor_features_by_cell: dict[str, SensorFeatures] = Field(default_factory=dict)

    # Outputs
    cell_results: list[CellRiskRecord] = Field(default_factory=list)
    assessment: AggregateAssessment | None = None
    assessment_id: int | None = None
    dispatched_alerts: list[str] = Field(default_factory=list)

    # Free-form diagnostic notes
    notes: dict[str, Any] = Field(default_factory=dict)

    def with_update(self, **fields: Any) -> MonitoringContext:
        """Return a copy with ``fields`` applied (pydantic-friendly)."""
        return self.model_copy(update=fields)
