"""``limen-ops`` MCP tool bodies — plain async functions, no FastMCP here.

Read tools are thin queries over the operational tables (same SQL shapes as
the public API endpoints). The one mutating tool (``run_monitor``) is gated
by ``MCP_ADMIN_TOKEN`` exactly like the geodata MCP's ``refresh``: env var
unset ⇒ disabled (fail-closed).

Everything here is advisory/operator tooling: nothing participates in the
hourly scoring critical path, and nothing can alter a persisted score.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

ADMIN_TOKEN_ENV = "MCP_ADMIN_TOKEN"

_LEVELS = ("None", "Low", "Moderate", "High", "VeryHigh")


class AdminAuthError(Exception):
    """Raised when a mutating tool is called without a valid admin token."""


def check_admin_token(token: str | None) -> None:
    """Fail-closed gate: env unset ⇒ always denied."""
    expected = os.environ.get(ADMIN_TOKEN_ENV, "").strip()
    if not expected:
        raise AdminAuthError(
            f"mutating tools are disabled: {ADMIN_TOKEN_ENV} is not set on the server"
        )
    if not token or token != expected:
        raise AdminAuthError("invalid admin token")


def _coerce_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            out = json.loads(value)
            return out if isinstance(out, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def risk_summary(aoi_id: str | None = None) -> list[dict[str, Any]]:
    """Latest assessment summary per AOI: when, cells per level, max score."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT g.aoi_id, MAX(ra.computed_at) AS ts
                FROM risk_assessments ra
                JOIN grid_cells g ON g.id = ra.cell_id
                WHERE ($1::text IS NULL OR g.aoi_id = $1)
                GROUP BY g.aoi_id
            )
            SELECT g.aoi_id, l.ts AS computed_at,
                   COUNT(*) AS cells,
                   MAX(ra.score) AS max_score,
                   COUNT(*) FILTER (WHERE ra.class IN ('High','VeryHigh')) AS high_or_above,
                   COUNT(*) FILTER (WHERE ra.class = 'Moderate') AS moderate
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            JOIN latest l ON l.aoi_id = g.aoi_id AND l.ts = ra.computed_at
            GROUP BY g.aoi_id, l.ts
            ORDER BY high_or_above DESC, max_score DESC
            """,
            aoi_id,
        )
    return [
        {
            "aoi_id": str(r["aoi_id"]),
            "computed_at": r["computed_at"].isoformat(),
            "cells_scored": int(r["cells"]),
            "max_score": round(float(r["max_score"]), 3),
            "high_or_above": int(r["high_or_above"]),
            "moderate": int(r["moderate"]),
        }
        for r in rows
    ]


async def top_risk_cells(limit: int = 10, aoi_id: str | None = None) -> list[dict[str, Any]]:
    """Highest-scoring cells from each AOI's latest assessment (national ranking)."""
    limit = max(1, min(int(limit), 100))
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH latest AS (
                SELECT g.aoi_id, MAX(ra.computed_at) AS ts
                FROM risk_assessments ra
                JOIN grid_cells g ON g.id = ra.cell_id
                GROUP BY g.aoi_id
            )
            SELECT ra.cell_id, g.aoi_id, ra.score, ra.class, ra.computed_at
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            JOIN latest l ON l.aoi_id = g.aoi_id AND l.ts = ra.computed_at
            WHERE ($2::text IS NULL OR g.aoi_id = $2)
            ORDER BY ra.score DESC
            LIMIT $1
            """,
            limit,
            aoi_id,
        )
    return [
        {
            "cell_id": str(r["cell_id"]),
            "aoi_id": str(r["aoi_id"]),
            "score": round(float(r["score"]), 3),
            "level": str(r["class"]),
            "computed_at": r["computed_at"].isoformat(),
        }
        for r in rows
    ]


async def cell_breakdown(cell_id: str) -> dict[str, Any]:
    """Latest persisted per-component breakdown + briefing for one cell."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, computed_at, score, class, factors, explanation
            FROM risk_assessments
            WHERE cell_id = $1
            ORDER BY computed_at DESC
            LIMIT 1
            """,
            cell_id,
        )
    if row is None:
        return {"error": f"no assessment for cell {cell_id!r}"}
    return {
        "cell_id": str(row["cell_id"]),
        "computed_at": row["computed_at"].isoformat(),
        "score": round(float(row["score"]), 3),
        "level": str(row["class"]),
        "factors": _coerce_json(row["factors"]),
        "explanation": _coerce_json(row["explanation"]),
    }


async def recent_alerts(
    threshold: str = "Moderate", since_hours: int = 24, limit: int = 50
) -> list[dict[str, Any]]:
    """Cells at/above ``threshold`` in the last ``since_hours`` hours."""
    if threshold not in _LEVELS:
        threshold = "Moderate"
    levels = list(_LEVELS[_LEVELS.index(threshold) :])
    since_hours = max(1, min(int(since_hours), 24 * 30))
    limit = max(1, min(int(limit), 500))
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ra.cell_id, g.aoi_id, ra.score, ra.class, ra.computed_at
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE ra.class = ANY($1::text[])
              AND ra.computed_at >= now() - ($2::int * interval '1 hour')
            ORDER BY ra.computed_at DESC, ra.score DESC
            LIMIT $3
            """,
            levels,
            since_hours,
            limit,
        )
    return [
        {
            "cell_id": str(r["cell_id"]),
            "aoi_id": str(r["aoi_id"]),
            "score": round(float(r["score"]), 3),
            "level": str(r["class"]),
            "computed_at": r["computed_at"].isoformat(),
        }
        for r in rows
    ]


async def run_monitor(
    aoi_id: str, admin_token: str | None = None, cell_limit: int | None = None
) -> dict[str, Any]:
    """Run the full MAF workflow once for ``aoi_id`` (admin only)."""
    check_admin_token(admin_token)
    from limen.agents.workflows.main_workflow import build_landslide_workflow
    from limen.core.models.context import MonitoringContext

    workflow = build_landslide_workflow(cell_limit=cell_limit)
    ctx = MonitoringContext(aoi_id=aoi_id, valuation_time=datetime.now(UTC))
    result = await workflow.run(ctx)
    out = result.context
    log.info("mcp.run_monitor.done", aoi_id=aoi_id, cells=len(out.cell_results))
    return {
        "aoi_id": aoi_id,
        "assessment_id": out.assessment_id,
        "cells_scored": len(out.cell_results),
        "high_or_above": out.assessment.cells_high_or_above if out.assessment else 0,
        "dispatched_alerts": list(out.dispatched_alerts),
    }
