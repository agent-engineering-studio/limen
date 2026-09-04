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
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
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
        hazard_type=HazardType(row["hazard_type"]),
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
async def latest_assessment(
    aoi_id: str,
    deps: DepsDep,  # noqa: ARG001 — DI presence
    hazard: HazardType = DEFAULT_HAZARD,
) -> LatestAssessmentResponse:
    """Return the latest persisted assessment (one row per cell) for ``aoi_id``.

    ``hazard`` is validated by FastAPI against the enum, so an unknown value
    is a 422 and needs no hand-written check.
    """
    async with acquire() as conn:
        latest_ts = await conn.fetchval(
            """
            SELECT MAX(ra.computed_at)
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = $1 AND ra.hazard_type = $2
            """,
            aoi_id,
            hazard.value,
        )
        if latest_ts is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no {hazard.value} assessment for AOI {aoi_id!r}",
            )
        rows = await conn.fetch(
            """
            SELECT ra.cell_id, ra.hazard_type, ra.computed_at, ra.horizon,
                   ra.score, ra.class, ra.factors, ra.explanation,
                   ra.pipeline_version
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE g.aoi_id = $1 AND ra.computed_at = $2 AND ra.hazard_type = $3
            ORDER BY ra.score DESC
            """,
            aoi_id,
            latest_ts,
            hazard.value,
        )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no {hazard.value} assessment for AOI {aoi_id!r}",
        )

    records = [_record_from_row(r) for r in rows]
    explanation = _coerce_json(rows[0]["explanation"])
    analysis_payload = explanation.get("analysis")
    analysis = RiskAnalysisDTO.model_validate(analysis_payload) if analysis_payload else None

    by_level = Counter(r.level.value for r in records)
    high_or_above = sum(1 for r in records if r.level in {RiskLevel.High, RiskLevel.VeryHigh})

    return LatestAssessmentResponse(
        aoi_id=aoi_id,
        hazard_type=hazard,
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
async def cell_breakdown(
    cell_id: str,
    deps: DepsDep,  # noqa: ARG001 — DI presence
    hazard: HazardType = DEFAULT_HAZARD,
) -> CellBreakdownResponse:
    """Return the latest persisted breakdown for ``cell_id``."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, hazard_type, computed_at, horizon, score, class,
                   factors, explanation, pipeline_version
            FROM risk_assessments
            WHERE cell_id = $1 AND hazard_type = $2
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            cell_id,
            hazard.value,
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no {hazard.value} breakdown for cell {cell_id!r}",
        )
    return CellBreakdownResponse(
        cell_id=str(row["cell_id"]),
        hazard_type=HazardType(row["hazard_type"]),
        computed_at=row["computed_at"],
        score=float(row["score"]),
        level=str(row["class"]),
        horizon=str(row["horizon"]),
        pipeline_version=str(row["pipeline_version"]),
        factors=_coerce_json(row["factors"]),
        explanation=_coerce_json(row["explanation"]),
    )


@router.get("/api/hazards")
async def hazards(response: Response) -> dict[str, Any]:
    """Hazards this deployment can actually score, with their Italian labels.

    Read from the ``hazards`` table rather than from ``HAZARDS__ENABLED``
    (the table is what ``mv_latest_risk`` cross-joins), and filtered to the
    ones that are scorable: a hazard enabled in the table but missing its
    thresholds file would be offered to the SPA selector and then 404 on its
    own legend.
    """
    from limen.data.repos.hazards_repo import scorable_with_labels

    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "items": [
            {"hazard": hazard.value, "label_it": label}
            for hazard, label in await scorable_with_labels()
        ],
        "default": DEFAULT_HAZARD.value,
    }


@router.get("/api/legend")
async def legend(response: Response, hazard: HazardType = DEFAULT_HAZARD) -> dict[str, Any]:
    """Class cutoffs + Protezione Civile alert colours (presentation only).

    Per hazard: the class cutoffs and the civil-protection mapping live in
    each hazard's own YAML, so a legend built from the landslide file would
    mislabel another hazard's colours.
    """
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    response.headers["Cache-Control"] = "public, max-age=3600"
    try:
        t = load_hazard_thresholds(hazard)
    except FileNotFoundError:
        # Il nome è valido nell'enum ma questo deployment non lo configura:
        # è un 404, non un errore del server.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"nessuna legenda per il pericolo {hazard.value!r} in questo deployment",
        ) from None
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
        # Model card for the public "Il modello, spiegato" page (issue #16):
        # the exact versioned weights/thresholds so the SPA draws its charts
        # from the YAML source of truth, never hard-coded numbers in the TSX.
        "model": {
            "weights": {
                "static": t.weights.static,
                "meteo": t.weights.meteo,
                "seismic": t.weights.seismic,
                "fire": t.weights.fire,
                "hydrology": t.weights.hydrology,
            },
            "meteo_weights": {
                "caine": t.meteo.weights.caine,
                "api": t.meteo.weights.api,
                "soil": t.meteo.weights.soil,
            },
            "caine": {
                "macroregions": {
                    name: {"alpha": mr.alpha, "beta": mr.beta}
                    for name, mr in t.caine.macroregions.items()
                },
            },
            "api": {
                "sigmoid_sigma_mm": t.api.sigmoid_sigma_mm,
                "baseline_fallback_mm": t.api.baseline.fallback_mm,
            },
            "soil": {
                "sigmoid_center": t.soil.sigmoid_center,
                "sigmoid_steepness": t.soil.sigmoid_steepness,
            },
            "seismic": {
                "tau_days": t.seismic.tau_days,
                "pga_threshold_g": t.seismic.pga_threshold_g,
                "pga_scale_g": t.seismic.pga_scale_g,
            },
            "post_fire": {
                "peak_months": t.post_fire.peak_months,
                "curve_denominator": t.post_fire.curve_denominator,
                "window_months_max": t.post_fire.window_months_max,
            },
        },
    }


@router.get("/api/report/national")
async def national_report_endpoint(response: Response) -> dict[str, Any]:
    """Aggregated national picture — same payload as the MCP tool.

    Landslide only in Fase 1: the national rollup reads the comune view and
    the shadow tables, both pinned to the default hazard by migration 028.
    The multi-hazard national report is #58 (Fase 4).
    """
    from limen.mcp.tools import national_report

    # The picture changes at most hourly; 60 s keeps repeat navigation
    # instant without hiding fresh sweeps.
    response.headers["Cache-Control"] = "public, max-age=60"
    return await national_report()


@router.get("/api/shadow/summary")
async def shadow_summary(
    response: Response, aoi: str | None = None, since: str | None = None
) -> dict[str, Any]:
    """Champion (V1) vs shadow challenger (ML) diagnostics (issue #4/#26).

    NON-authoritative: the ML challenger never drives alerts. The frontend
    renders this behind the authenticated dashboard, clearly labelled as
    diagnostics. Reuses the same aggregation as ``limen shadow-report``.
    """
    from datetime import UTC, datetime

    from limen.ml.shadow import DEFAULT_SINCE, collect_shadow_summary

    cutoff = DEFAULT_SINCE
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="`since` must be ISO 8601",
            ) from exc
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        # Pre-fix rows (rain features at zero, 7d19fe4) must never be judged.
        cutoff = max(cutoff, DEFAULT_SINCE)

    response.headers["Cache-Control"] = "public, max-age=300"
    async with acquire() as conn:
        summary = await collect_shadow_summary(conn, since=cutoff, aoi_filter=aoi)

    return {
        "since": summary.since.isoformat(),
        "aoi_filter": summary.aoi_filter,
        "model_versions": summary.model_versions,
        "total_pairs": summary.total_pairs,
        "regions": [
            {
                "aoi_id": s.aoi_id,
                "aoi_name": s.aoi_name,
                "n": s.n,
                "mean_abs_div": s.mean_abs_div,
                "p95_abs_div": s.p95_abs_div,
                "max_abs_div": s.max_abs_div,
                "correlation": s.correlation,
                "class_agreement": s.class_agreement,
            }
            for s in summary.stats
        ],
        "truth_events": [
            {
                "cell_id": r["cell_id"],
                "aoi_id": r["aoi_id"],
                "aoi_name": r["aoi_name"],
                "event_time": r["event_time"].isoformat(),
                "champion_score": (
                    float(r["champion_score"]) if r["champion_score"] is not None else None
                ),
                "ml_probability": (
                    float(r["ml_probability"]) if r["ml_probability"] is not None else None
                ),
            }
            for r in summary.truth_rows
        ],
    }


_CELL_OBSERVED_SQL = """
SELECT computed_at, score, class
FROM risk_assessments
WHERE cell_id = $1
  AND hazard_type = $3
  AND horizon NOT LIKE '+%'
  AND computed_at >= now() - make_interval(hours => $2::int)
ORDER BY computed_at
"""

_CELL_FORECAST_SQL = """
SELECT computed_at, horizon, score, class
FROM risk_assessments
WHERE cell_id = $1 AND hazard_type = $2 AND pipeline_version LIKE 'v1-forecast+%'
ORDER BY horizon
"""


@router.get("/api/cell/{cell_id}/history")
async def cell_history(
    cell_id: str,
    response: Response,
    hours: int = 72,
    hazard: HazardType = DEFAULT_HAZARD,
) -> dict[str, Any]:
    """Per-cell risk trend: observed (past `hours`) + forecast (+24/48/72h) (#41).

    Forecast rows carry the run time in ``computed_at`` and the offset in
    ``horizon`` (e.g. ``+48h``); the target time is ``computed_at + offset``.
    """
    from datetime import timedelta

    response.headers["Cache-Control"] = "public, max-age=120"
    async with acquire() as conn:
        obs = await conn.fetch(_CELL_OBSERVED_SQL, cell_id, hours, hazard.value)
        fc = await conn.fetch(_CELL_FORECAST_SQL, cell_id, hazard.value)

    observed = [
        {"t": r["computed_at"].isoformat(), "score": float(r["score"]), "level": r["class"]}
        for r in obs
    ]
    forecast: list[dict[str, Any]] = []
    for r in fc:
        offset_h = int(str(r["horizon"]).lstrip("+").rstrip("h") or 0)
        target = r["computed_at"] + timedelta(hours=offset_h)
        forecast.append({"t": target.isoformat(), "score": float(r["score"]), "level": r["class"]})
    forecast.sort(key=lambda x: x["t"])
    return {"observed": observed, "forecast": forecast}


@router.get("/api/shadow/reliability")
async def shadow_reliability(
    response: Response, aoi: str | None = None, since: str | None = None
) -> dict[str, Any]:
    """ML challenger calibration curve (issue #30/#26). NON-authoritative.

    Gated on data: with too few real landslide outcomes the diagram is noise, so
    ``sufficient`` is False and the frontend shows an insufficient-data state.
    """
    from datetime import UTC, datetime

    from limen.config.settings import Settings
    from limen.ml.shadow import DEFAULT_SINCE, collect_reliability

    cutoff = DEFAULT_SINCE
    if since:
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="`since` must be ISO 8601",
            ) from exc
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        cutoff = max(cutoff, DEFAULT_SINCE)

    response.headers["Cache-Control"] = "public, max-age=300"
    async with acquire() as conn:
        rel = await collect_reliability(
            conn, since=cutoff, aoi_filter=aoi, radius_m=Settings().verify.match_radius_m
        )
    return {
        "sufficient": rel.sufficient,
        "n_positives": rel.n_positives,
        "min_positives": rel.min_positives,
        "bins": [
            {
                "lo": b.lo,
                "hi": b.hi,
                "predicted_mean": b.predicted_mean,
                "observed_freq": b.observed_freq,
                "count": b.count,
            }
            for b in rel.bins
        ],
    }
