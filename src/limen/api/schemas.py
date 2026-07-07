"""Pydantic v2 request/response schemas for the API layer.

Kept small on purpose — the heavy DTOs (RiskScore, breakdowns,
MonitoringContext, AggregateAssessment) already live in
:mod:`limen.core.models` and are reused verbatim.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
    RiskAnalysisDTO,
)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    pool: bool
    cache: bool
    llm_provider: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    pool: bool
    migrations: bool
    detail: str | None = None


class AoiSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str | None = None
    kind: str | None = None


class AoiListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AoiSummary]


class MonitorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_limit: int | None = Field(
        default=None,
        ge=1,
        description="Optional cap on the number of cells scored (smoke runs).",
    )
    valuation_time: datetime | None = None


class MonitorResponse(BaseModel):
    """Wrap-up of one workflow run."""

    model_config = ConfigDict(extra="forbid")

    aoi_id: str
    assessment_id: int | None = None
    assessment: AggregateAssessment | None = None
    cells_scored: int = 0
    high_or_above: int = 0
    dispatched_alerts: list[str] = Field(default_factory=list)


class LatestAssessmentResponse(BaseModel):
    """Latest persisted assessment summary for an AOI."""

    model_config = ConfigDict(extra="forbid")

    aoi_id: str
    horizon: str
    pipeline_version: str
    computed_at: datetime
    cells: list[CellRiskRecord]
    cells_high_or_above: int
    cells_by_level: dict[str, int]
    briefing_it: str | None = None
    analysis: RiskAnalysisDTO | None = None


class CellBreakdownResponse(BaseModel):
    """Per-cell breakdown of the latest scoring run."""

    model_config = ConfigDict(extra="forbid")

    cell_id: str
    computed_at: datetime
    score: float
    level: str
    horizon: str
    pipeline_version: str
    factors: dict[str, object]
    explanation: dict[str, object]


class AlertItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    aoi_id: str | None = None
    score: float
    level: str
    computed_at: datetime
    lon: float | None = None
    lat: float | None = None
    # Nome del comune (ISTAT) del centroide — leggibile per non esperti.
    place: str | None = None
    # "abitato" quando la cella ricade su tessuto urbano CORINE (1xx).
    exposure: str | None = None


class AlertsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AlertItem]
