"""Risk lookup endpoints — latest AOI assessment + per-cell breakdown."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from limen.api.dependencies import DepsDep
from limen.api.schemas import (
    CellBreakdownResponse,
    LatestAssessmentResponse,
)
from limen.core.models.context import CellRiskRecord, RiskAnalysisDTO
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)
from limen.data.db import acquire

router = APIRouter(tags=["risk"])


def _coerce_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return dict(json.loads(value))


def _record_from_row(row: Any) -> CellRiskRecord:
    factors = _coerce_json(row["factors"])
    static_terms = factors.get("static_terms") or {}
    meteo_terms = dict(factors.get("meteo_terms") or {})
    # measured_overrides round-trips through JSON as a list; the DTO is a tuple.
    if "measured_overrides" in meteo_terms:
        meteo_terms["measured_overrides"] = tuple(meteo_terms["measured_overrides"])
    return CellRiskRecord(
        cell_id=str(row["cell_id"]),
        score=float(row["score"]),
        level=RiskLevel(row["class"]),
        s=float(factors.get("s", 0.0)),
        m=float(factors.get("m", 0.0)),
        e=float(factors.get("e", 0.0)),
        f=float(factors.get("f", 0.0)),
        h=float(factors.get("h", 0.0)),
        static_terms=StaticBreakdown(**static_terms)
        if static_terms
        else StaticBreakdown(
            susc_ispra=0.0, iffi_density=0.0, slope=0.0, pai=0.0, litho_weight=0.0
        ),
        meteo_terms=MeteoBreakdown(**meteo_terms)
        if meteo_terms
        else MeteoBreakdown(caine_excess=0.0, caine_norm=0.0, api_factor=0.5, soil_factor=0.5),
    )


@router.get("/api/aoi/{aoi_id}/risk/latest", response_model=LatestAssessmentResponse)
async def latest_assessment(aoi_id: str, deps: DepsDep) -> LatestAssessmentResponse:  # noqa: ARG001
    """Return the latest persisted assessment (one row per cell) for ``aoi_id``."""
    async with acquire() as conn:
        latest_ts = await conn.fetchval(
            """
            SELECT MAX(ra.computed_at)
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = $1
            """,
            aoi_id,
        )
        if latest_ts is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no assessment for AOI {aoi_id!r}",
            )
        rows = await conn.fetch(
            """
            SELECT ra.cell_id, ra.computed_at, ra.horizon, ra.score, ra.class,
                   ra.factors, ra.explanation, ra.pipeline_version
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = $1 AND ra.computed_at = $2
            ORDER BY ra.score DESC
            """,
            aoi_id,
            latest_ts,
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no assessment for AOI {aoi_id!r}",
        )

    records = [_record_from_row(r) for r in rows]
    explanation = _coerce_json(rows[0]["explanation"])
    analysis_payload = explanation.get("analysis")
    analysis = RiskAnalysisDTO.model_validate(analysis_payload) if analysis_payload else None

    by_level = Counter(r.level.value for r in records)
    high_or_above = sum(1 for r in records if r.level in {RiskLevel.High, RiskLevel.VeryHigh})

    return LatestAssessmentResponse(
        aoi_id=aoi_id,
        horizon=str(rows[0]["horizon"]),
        pipeline_version=str(rows[0]["pipeline_version"]),
        computed_at=rows[0]["computed_at"],
        cells=records,
        cells_high_or_above=high_or_above,
        cells_by_level=dict(by_level),
        briefing_it=str(explanation.get("briefing_it")) if explanation.get("briefing_it") else None,
        analysis=analysis,
    )


@router.get("/api/cell/{cell_id}/breakdown", response_model=CellBreakdownResponse)
async def cell_breakdown(cell_id: str, deps: DepsDep) -> CellBreakdownResponse:  # noqa: ARG001
    """Return the latest persisted breakdown for ``cell_id``."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, computed_at, horizon, score, class,
                   factors, explanation, pipeline_version
            FROM risk_assessments
            WHERE cell_id = $1
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            cell_id,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no breakdown for cell {cell_id!r}",
        )
    return CellBreakdownResponse(
        cell_id=str(row["cell_id"]),
        computed_at=row["computed_at"],
        score=float(row["score"]),
        level=str(row["class"]),
        horizon=str(row["horizon"]),
        pipeline_version=str(row["pipeline_version"]),
        factors=_coerce_json(row["factors"]),
        explanation=_coerce_json(row["explanation"]),
    )


@router.get("/api/legend")
async def legend(response: Response) -> dict[str, Any]:
    """Class cutoffs + Protezione Civile alert colours (presentation only)."""
    from limen.core.scoring.regional_thresholds import load_regional_thresholds

    response.headers["Cache-Control"] = "public, max-age=3600"
    t = load_regional_thresholds()
    pc = t.pc_alert
    levels = {
        "none": "None",
        "low": "Low",
        "moderate": "Moderate",
        "high": "High",
        "very_high": "VeryHigh",
    }
    return {
        "classes": [
            {
                "level": level,
                "lo": getattr(t.classes, key).lo,
                "hi": getattr(t.classes, key).hi,
                "pc_alert": getattr(pc, key),
            }
            for key, level in levels.items()
        ],
        "model_version": t.model_version,
    }


@router.get("/api/report/national")
async def national_report_endpoint(response: Response) -> dict[str, Any]:
    """Aggregated national picture — same payload as the MCP tool."""
    from limen.mcp.tools import national_report

    # The picture changes at most hourly; 60 s keeps repeat navigation
    # instant without hiding fresh sweeps.
    response.headers["Cache-Control"] = "public, max-age=60"
    return await national_report()
