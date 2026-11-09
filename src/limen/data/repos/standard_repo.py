"""Le righe di ``mv_comune_risk`` per le uscite standard (#499 CAP, #503 OGC).

``measured IS NOT FALSE``: un comune il cui pericolo non è stato misurato non
è «tranquillo» né «in allerta», e nessuna delle due uscite deve dirlo
(«Non misurato non è nessun pericolo»).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from limen.core.models.hazard import HazardType
from limen.core.standard.cap import ComuneInAllerta
from limen.core.standard.ogc import Filtro
from limen.data.db import acquire

#: Tolleranza della semplificazione delle geometrie comunali, in gradi
#: (~100 m): un comune servito intero pesa fino a centinaia di kB.
_SEMPLIFICA_GRADI = 0.001

_ALLERTA = """
    SELECT istat_code, name, hazard_type::text AS hazard, worst_class, max_score,
           n_cells, n_alert, computed_at
      FROM mv_comune_risk
     WHERE worst_class = ANY($1::text[])
       AND measured IS NOT FALSE
       AND computed_at IS NOT NULL
"""


def _in_allerta(r: Any) -> ComuneInAllerta:
    return ComuneInAllerta(
        istat_code=str(r["istat_code"]),
        name=str(r["name"]),
        hazard=HazardType(r["hazard"]),
        worst_class=str(r["worst_class"]),
        max_score=float(r["max_score"] or 0.0),
        n_cells=int(r["n_cells"]),
        n_alert=int(r["n_alert"]),
        computed_at=r["computed_at"],
    )


async def comuni_in_allerta(classi: list[str]) -> list[ComuneInAllerta]:
    async with acquire() as conn:
        rows = await conn.fetch(
            _ALLERTA + " ORDER BY max_score DESC, istat_code, hazard_type", classi
        )
    return [_in_allerta(r) for r in rows]


async def comune_in_allerta(
    classi: list[str], hazard: HazardType, istat_code: str
) -> ComuneInAllerta | None:
    async with acquire() as conn:
        r = await conn.fetchrow(
            _ALLERTA + " AND hazard_type = $2::hazard_type AND istat_code = $3",
            classi,
            hazard.value,
            istat_code,
        )
    return None if r is None else _in_allerta(r)


_DOVE = """
     WHERE hazard_type = $1::hazard_type
       AND ($2::float8 IS NULL OR geom && ST_MakeEnvelope($2, $3, $4, $5, 4326))
       AND ($6::timestamptz IS NULL OR computed_at >= $6)
       AND ($7::timestamptz IS NULL OR computed_at <= $7)
"""


def _parametri(hazard: HazardType, f: Filtro) -> list[Any]:
    b: tuple[float | None, ...] = f.bbox or (None, None, None, None)
    return [hazard.value, *b, f.dal, f.al]


def _oggetto(r: Any) -> dict[str, Any]:
    geom = r["geometry"]
    return {
        "istat_code": r["istat_code"],
        "name": r["name"],
        "aoi_id": r["aoi_id"],
        "worst_class": r["worst_class"],
        "max_score": None if r["max_score"] is None else round(float(r["max_score"]), 3),
        "n_cells": int(r["n_cells"]),
        "n_alert": int(r["n_alert"]),
        "measured": r["measured"],
        "computed_at": r["computed_at"],
        "geometry": json.loads(geom) if isinstance(geom, str) else geom,
    }


_COLONNE = f"""
    SELECT istat_code, name, aoi_id, worst_class, max_score, n_cells, n_alert, measured,
           computed_at,
           ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom, {_SEMPLIFICA_GRADI}), 5) AS geometry
      FROM mv_comune_risk
"""


async def comuni(hazard: HazardType, f: Filtro) -> tuple[list[dict[str, Any]], int]:
    """Una pagina di comuni per la collezione del pericolo, e quanti in tutto."""
    p = _parametri(hazard, f)
    async with acquire() as conn:
        totale = await conn.fetchval("SELECT count(*) FROM mv_comune_risk" + _DOVE, *p)
        rows = await conn.fetch(
            _COLONNE + _DOVE + " ORDER BY istat_code LIMIT $8 OFFSET $9", *p, f.limit, f.offset
        )
    return [_oggetto(r) for r in rows], int(totale or 0)


async def comune(hazard: HazardType, istat_code: str) -> dict[str, Any] | None:
    async with acquire() as conn:
        r = await conn.fetchrow(
            _COLONNE + " WHERE hazard_type = $1::hazard_type AND istat_code = $2",
            hazard.value,
            istat_code,
        )
    return None if r is None else _oggetto(r)


async def ultimo_calcolo() -> datetime | None:
    async with acquire() as conn:
        t = await conn.fetchval("SELECT max(computed_at) FROM mv_comune_risk")
    return t if isinstance(t, datetime) else None
