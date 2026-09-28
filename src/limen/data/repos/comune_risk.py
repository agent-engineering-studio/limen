"""Letture su `mv_comune_risk`: la classifica e il dettaglio di un comune.

Dalla migrazione 051 il rollup ha una riga per **(comune, pericolo)**, e
queste query ne ricompongono una per comune con i tre indicatori affiancati:
è la forma che la colonna della dashboard disegna, e farla qui evita alla
pagina tre richieste per dire una riga.
"""

from __future__ import annotations

import json
from typing import Any

from limen.data.db import acquire

#: Ordine delle classi, per scegliere il peggiore fra i pericoli. In SQL
#: perché è lì che si ordina: portarlo in Python vorrebbe dire leggere tutti
#: i comuni per mostrarne cinquanta.
_RANK = """
    CASE worst_class
        WHEN 'VeryHigh' THEN 4
        WHEN 'High'     THEN 3
        WHEN 'Moderate' THEN 2
        WHEN 'Low'      THEN 1
        ELSE 0
    END
"""

#: Una riga per comune: i tre pericoli in un oggetto, più il peggiore
#: ricomposto per l'ordinamento e per i consumatori che leggevano la forma
#: a pericolo unico.
_PER_COMUNE = f"""
SELECT
    istat_code,
    name,
    aoi_id,
    jsonb_object_agg(
        hazard_type::text,
        jsonb_build_object(
            'class',   worst_class,
            'score',   round(COALESCE(max_score, 0)::numeric, 3),
            'n_cells', n_cells,
            'n_alert', n_alert
        )
    ) AS hazards,
    -- Il peggiore fra i pericoli: è ciò che ordina la classifica e ciò che
    -- i consumatori a pericolo unico leggevano come `worst_class`.
    (array_agg(hazard_type::text ORDER BY {_RANK} DESC, max_score DESC NULLS LAST,
               hazard_type::text))[1] AS worst_hazard,
    (array_agg(worst_class ORDER BY {_RANK} DESC, max_score DESC NULLS LAST,
               hazard_type::text))[1] AS worst_class,
    max(COALESCE(max_score, 0))            AS max_score,
    max({_RANK})                           AS worst_rank,
    max(n_cells)                           AS n_cells,
    sum(n_alert)                           AS n_alert,
    sum(n_none)                            AS n_none,
    sum(n_low)                             AS n_low,
    sum(n_moderate)                        AS n_moderate,
    sum(n_high)                            AS n_high,
    sum(n_veryhigh)                        AS n_veryhigh,
    max(exposure_rank)                     AS exposure_rank
FROM mv_comune_risk
GROUP BY istat_code, name, aoi_id
"""


def _to_comune(row: Any) -> dict[str, Any]:
    hazards = row["hazards"]
    if isinstance(hazards, str):  # asyncpg restituisce jsonb come testo
        hazards = json.loads(hazards)
    return {
        "istat_code": row["istat_code"],
        "name": row["name"],
        "aoi_id": row["aoi_id"],
        "worst_hazard": row["worst_hazard"],
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
        # I tre indicatori affiancati: la riga della dashboard li mostra tutti,
        # anche a zero, perché un trattino è una risposta e una colonna che
        # sparisce non lo è.
        "hazards": {
            h: {
                "class": str(v["class"]),
                "score": round(float(v["score"] or 0.0), 3),
                "n_cells": int(v["n_cells"]),
                "n_alert": int(v["n_alert"]),
            }
            for h, v in hazards.items()
        },
    }


async def top_comuni(
    *,
    aoi_id: str | None,
    limit: int,
    min_rank: int = 2,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """I comuni ordinati dal peggiore, su tutti i pericoli.

    `min_rank` è la soglia sotto cui un comune non entra in classifica: 2 è
    «Moderato», che è dove il sistema comincia a dire qualcosa. Con `query`
    la soglia non si applica — chi cerca il proprio comune per nome vuole
    vederlo comunque, anche quando non ha niente da segnalare, e quello è il
    caso in cui la risposta «nessun pericolo sopra soglia» è la notizia.
    """
    limit = max(1, min(limit, 200))
    async with acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH per_comune AS ({_PER_COMUNE})
            SELECT * FROM per_comune
            WHERE ($1::text IS NULL OR aoi_id = $1)
              AND ($3::text IS NULL OR name ILIKE '%' || $3 || '%')
              AND ($3::text IS NOT NULL OR worst_rank >= $4)
            ORDER BY worst_rank DESC, exposure_rank DESC, n_alert DESC,
                     max_score DESC, name
            LIMIT $2
            """,
            aoi_id,
            limit,
            query,
            min_rank,
        )
    return [_to_comune(r) for r in rows]


async def comune_detail(istat_code: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"WITH per_comune AS ({_PER_COMUNE}) SELECT * FROM per_comune WHERE istat_code = $1",
            istat_code,
        )
        if row is None:
            return None
        cells = await conn.fetch(
            """
            SELECT m.cell_id, m.hazard_type::text AS hazard, m.score, m.class AS level,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM cell_comune cc
            JOIN latest_risk m ON m.cell_id = cc.cell_id
            JOIN grid_cells g ON g.id = cc.cell_id
            WHERE cc.istat_code = $1 AND m.score IS NOT NULL
            ORDER BY m.score DESC NULLS LAST, m.cell_id
            LIMIT 200
            """,
            istat_code,
        )
    out = _to_comune(row)
    return {
        "comune": out,
        "cells": [
            {
                "cell_id": str(c["cell_id"]),
                "hazard": str(c["hazard"]),
                "score": round(float(c["score"]), 3),
                "level": str(c["level"]),
                "lon": float(c["lon"]),
                "lat": float(c["lat"]),
            }
            for c in cells
        ],
    }
