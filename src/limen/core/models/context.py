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

from limen.core.models.risk import (
    KinematicBreakdown,
    MeteoBreakdown,
    RiskLevel,
    SeismicHistoryEvent,
    StaticBreakdown,
    StaticFactors,
)
from limen.core.models.sensor import SensorFeatures


class CellRiskRecord(BaseModel):
    """One per-cell scoring result inside the assessment."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    level: RiskLevel
    static_terms: StaticBreakdown
    meteo_terms: MeteoBreakdown
    s: float = Field(..., ge=0.0, le=1.0)
    m: float = Field(..., ge=0.0, le=1.0)
    e: float = Field(..., ge=0.0, le=1.0)
    f: float = Field(..., ge=0.0, le=1.0)
    h: float = Field(..., ge=0.0, le=1.0)
    # V1.5 — present only on monitored cells (in-situ regime).
    k: float = Field(default=0.0, ge=0.0, le=1.0)
    kinematic_terms: KinematicBreakdown | None = None
    monitored: bool = False
    hard_escalation: bool = False


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
