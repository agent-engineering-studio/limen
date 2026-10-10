"""I numeri di una cella per il contributo di un esperto: si leggono, non si salvano."""

from __future__ import annotations

import json
from typing import Any

from limen.data.db import acquire


async def stato_cella(cell_id: str) -> dict[str, Any] | None:
    """I numeri della cella come li vede la mappa adesso; ``None`` se non esiste."""
    async with acquire() as conn:
        cella = await conn.fetchrow(
            """
            SELECT aoi_id, ST_X(centroid) AS lon, ST_Y(centroid) AS lat
            FROM grid_cells WHERE id = $1
            """,
            cell_id,
        )
        if cella is None:
            return None
        righe = await conn.fetch(
            """
            SELECT hazard_type, score, class, computed_at, factors
            FROM latest_risk WHERE cell_id = $1
            ORDER BY hazard_type
            """,
            cell_id,
        )
    pericoli = []
    for r in righe:
        factors = r["factors"]
        if isinstance(factors, str):
            factors = json.loads(factors)
        pericoli.append(
            {
                "hazard": str(r["hazard_type"]),
                "score": r["score"],
                "classe": r["class"],
                "calcolato": r["computed_at"].isoformat(),
                "fattori": factors,
            }
        )
    return {
        "aoi_id": str(cella["aoi_id"]),
        "lon": float(cella["lon"]),
        "lat": float(cella["lat"]),
        "pericoli": pericoli,
    }
