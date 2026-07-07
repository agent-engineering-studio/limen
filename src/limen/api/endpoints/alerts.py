"""Recent alerts endpoint — high-or-above persisted assessments."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Response

from limen.api.dependencies import DepsDep
from limen.api.schemas import AlertItem, AlertsResponse
from limen.data.db import acquire

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertsResponse)
async def list_alerts(
    response: Response,
    deps: DepsDep,  # noqa: ARG001 — DI presence
    threshold: str = Query("High", description="Minimum risk level to include"),
    since_hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(200, ge=1, le=2000),
) -> AlertsResponse:
    """Return the most recent persisted alerts above ``threshold``."""
    response.headers["Cache-Control"] = "public, max-age=30"
    valid = {"None", "Low", "Moderate", "High", "VeryHigh"}
    if threshold not in valid:
        threshold = "High"

    # Levels at or above the requested threshold. Order is fixed so we
    # can short-circuit on string equality in the WHERE clause.
    order = ["None", "Low", "Moderate", "High", "VeryHigh"]
    levels_to_include = order[order.index(threshold) :]

    # Latest row per cell (repeat hourly ticks would flood the list with
    # duplicates), ranked by score so the worst cells come first. The
    # centroid lets the UI fly to / highlight the cell on the map.
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT DISTINCT ON (ra.cell_id)
                       ra.cell_id, ra.score, ra.class, ra.computed_at
                FROM risk_assessments ra
                WHERE ra.class = ANY($1::text[])
                  AND ra.computed_at >= now() - ($2::int * interval '1 hour')
                ORDER BY ra.cell_id, ra.computed_at DESC
            )
            -- Esposizione dal CORINE: 11x tessuto urbano, 12x
            -- infrastrutture principali (strade/ferrovie 122,
            -- industriale 121, porti/aeroporti 123-124) — nella cella
            -- stessa e nelle adiacenti (~2 km). Calcolata DOPO la
            -- dedup: solo sulle celle uniche, non su ogni tick orario.
            SELECT l.cell_id, g.aoi_id, l.score, l.class, l.computed_at,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat,
                   (csf.landuse_code LIKE '11%') AS urban_here,
                   (csf.landuse_code LIKE '12%') AS infra_here,
                   csf.near_urban AS urban_near,
                   csf.near_infra AS infra_near
            FROM latest l
            JOIN grid_cells g ON g.id = l.cell_id
            LEFT JOIN cell_static_factors csf ON csf.cell_id = l.cell_id
            """,
            levels_to_include,
            since_hours,
        )

    # Priorità = rischio x (1 + esposizione): la stessa formula del
    # dispatcher degli alert. Una frana Moderate sopra un paese o una
    # statale conta più di una identica su un versante disabitato.
    def _exposure(r: Any) -> tuple[float, list[str]]:
        factor = 0.0
        tags: list[str] = []
        if r["urban_here"]:
            factor += 1.0
            tags.append("abitato")
        elif r["urban_near"]:
            factor += 0.5
            tags.append("vicino abitato")
        if r["infra_here"]:
            factor += 0.6
            tags.append("infrastrutture")
        elif r["infra_near"]:
            factor += 0.3
            tags.append("infrastrutture vicine")
        return min(factor, 2.0), tags

    scored = []
    for r in rows:
        factor, tags = _exposure(r)
        scored.append((float(r["score"]) * (1.0 + factor), tags, r))
    scored.sort(key=lambda t: t[0], reverse=True)
    scored = scored[:limit]

    from limen.integrations.geoserver_source.comuni import comuni_for_points

    places = await comuni_for_points([(float(r["lon"]), float(r["lat"])) for _, _, r in scored])

    items = [
        AlertItem(
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            score=float(r["score"]),
            level=str(r["class"]),
            computed_at=r["computed_at"],
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            place=place,
            exposure=", ".join(tags) if tags else None,
            priority=round(priority, 3),
        )
        for (priority, tags, r), place in zip(scored, places, strict=True)
    ]
    return AlertsResponse(items=items)


@router.get("/forecast")
async def list_forecast_alerts(
    deps: DepsDep,  # noqa: ARG001 — DI presence
    since_hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, list[dict[str, object]]]:
    """Predictive (PREVISIONE) dispatches from the forecast sweep."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, horizon_h, max_level, max_score,
                   cells_alerted, summary, dispatched_at
            FROM forecast_dispatches
            WHERE dispatched_at >= now() - make_interval(hours => $1)
            ORDER BY dispatched_at DESC
            LIMIT $2
            """,
            since_hours,
            limit,
        )
    return {
        "items": [
            {
                "aoi_id": str(r["aoi_id"]),
                "horizon_h": int(r["horizon_h"]),
                "max_level": str(r["max_level"]),
                "max_score": float(r["max_score"]),
                "cells_alerted": int(r["cells_alerted"]),
                "summary": r["summary"],
                "dispatched_at": r["dispatched_at"].isoformat(),
            }
            for r in rows
        ]
    }
