"""Read queries over mv_comune_risk (leaderboard + detail)."""

from __future__ import annotations

from typing import Any

from limen.data.db import acquire

_COLS = (
    "istat_code, name, aoi_id, worst_class, max_score, n_cells, n_alert, "
    "n_none, n_low, n_moderate, n_high, n_veryhigh, exposure_rank"
)


def _to_comune(row: Any) -> dict[str, Any]:
    return {
        "istat_code": row["istat_code"],
        "name": row["name"],
        "aoi_id": row["aoi_id"],
        "worst_class": row["worst_class"],
        "max_score": round(float(row["max_score"] or 0.0), 3),
        "n_cells": int(row["n_cells"]),
        "n_alert": int(row["n_alert"]),
        "counts": {
            "None": int(row["n_none"]),
            "Low": int(row["n_low"]),
            "Moderate": int(row["n_moderate"]),
            "High": int(row["n_high"]),
            "VeryHigh": int(row["n_veryhigh"]),
        },
        "exposure_rank": round(float(row["exposure_rank"] or 0.0), 3),
    }


async def top_comuni(*, aoi_id: str | None, limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 200))
    async with acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_COLS} FROM mv_comune_risk
            WHERE n_alert > 0 AND ($1::text IS NULL OR aoi_id = $1)
            ORDER BY exposure_rank DESC, n_alert DESC, max_score DESC
            LIMIT $2
            """,
            aoi_id,
            limit,
        )
    return [_to_comune(r) for r in rows]


async def comune_detail(istat_code: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_COLS} FROM mv_comune_risk WHERE istat_code = $1", istat_code
        )
        if row is None:
            return None
        cells = await conn.fetch(
            """
            SELECT m.cell_id, m.risk_score AS score, m.risk_level AS level
            FROM cell_comune cc
            JOIN mv_latest_risk m ON m.cell_id = cc.cell_id
            WHERE cc.istat_code = $1 AND m.risk_score IS NOT NULL
            ORDER BY m.risk_score DESC
            LIMIT 500
            """,
            istat_code,
        )
    return {
        "comune": _to_comune(row),
        "cells": [
            {"cell_id": c["cell_id"], "score": round(float(c["score"]), 3), "level": c["level"]}
            for c in cells
        ],
    }
