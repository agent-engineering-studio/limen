"""Le righe per le misure offline (#480): feature per cella e verità, in sola lettura.

* **Incendio**: positiva la cella coperta per almeno ``copertura`` da perimetri
  EFFIS con ``fire_date`` nel periodo; dominio, ogni cella con la feature.
* **Alluvione**: positiva la cella coperta per almeno ``copertura`` da aree
  allagate Copernicus EMS con ``event_time`` nel periodo; dominio, le sole
  celle dentro una maschera di osservazione dello stesso periodo — fuori dalle
  maschere nessuno ha guardato, e «non osservata» non è «asciutta».

Le aree in EPSG:3035. Più perimetri sovrapposti possono contare due volte la
stessa superficie: la quota si tronca a 1, e la soglia guarda solo se la
supera.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from limen.core.models.hazard import HazardType
from limen.data.db import acquire

#: Le misure su 312.000 celle escono dal timeout di default del pool.
_TIMEOUT_S = 1800.0

_VERITA = {
    HazardType.WILDFIRE: """
        COALESCE((
            SELECT sum(ST_Area(ST_Transform(ST_Intersection(g.geom, p.geom), 3035)))
              FROM fire_perimeters p
             WHERE p.geom && g.geom AND ST_Intersects(p.geom, g.geom)
               AND p.fire_date BETWEEN $1 AND $2
        ), 0)
    """,
    HazardType.FLOOD: """
        COALESCE((
            SELECT sum(ST_Area(ST_Transform(ST_Intersection(g.geom, e.geom), 3035)))
              FROM flood_events e
             WHERE e.geom && g.geom AND ST_Intersects(e.geom, g.geom)
               AND e.event_time::date BETWEEN $1 AND $2
        ), 0)
    """,
}

_DOMINIO = {
    HazardType.WILDFIRE: "TRUE",
    HazardType.FLOOD: """
        EXISTS (
            SELECT 1 FROM flood_observation_masks m
             WHERE m.geom && g.geom AND ST_Intersects(m.geom, g.centroid)
               AND m.observed_time::date BETWEEN $1 AND $2
        )
    """,
}


@dataclass(frozen=True, slots=True)
class CellaMisura:
    lon: float
    lat: float
    quota: float | None
    valore: float
    positiva: bool


async def colonne_numeriche() -> list[str]:
    """Le colonne numeriche di ``cell_static_factors``: le sole feature ammesse."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = 'cell_static_factors'
               AND data_type IN ('double precision', 'integer', 'numeric', 'real', 'bigint')
             ORDER BY column_name
            """
        )
    return [str(r["column_name"]) for r in rows]


async def celle(
    hazard: HazardType, feature: str, *, dal: date, al: date, copertura: float
) -> list[CellaMisura]:
    """Una riga per cella del dominio: centroide, quota, valore, positiva."""
    if hazard not in _VERITA:
        raise ValueError(f"nessuna verità per {hazard.value}")
    if feature not in await colonne_numeriche():
        raise ValueError(f"{feature!r} non è una colonna numerica di cell_static_factors")
    # `feature` è nel elenco delle colonne vere dello schema: l'interpolazione
    # non porta testo dall'esterno.
    sql = f"""
        SELECT ST_X(g.centroid) AS lon, ST_Y(g.centroid) AS lat, f.elevation_m AS quota,
               f.{feature}::float8 AS valore,
               LEAST(1.0, {_VERITA[hazard]} / ST_Area(ST_Transform(g.geom, 3035))) AS quota_coperta
          FROM grid_cells g
          JOIN cell_static_factors f ON f.cell_id = g.id
         WHERE f.{feature} IS NOT NULL AND {_DOMINIO[hazard]}
    """
    async with acquire() as conn:
        rows = await conn.fetch(sql, dal, al, timeout=_TIMEOUT_S)
    return [
        CellaMisura(
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            quota=None if r["quota"] is None else float(r["quota"]),
            valore=float(r["valore"]),
            positiva=float(r["quota_coperta"]) >= copertura,
        )
        for r in rows
    ]
