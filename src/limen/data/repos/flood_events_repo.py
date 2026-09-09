"""Catalogo datato di eventi alluvionali — il truth set del backtest (#64).

Stessa forma di :mod:`limen.data.repos.landslide_events_repo`, con una
differenza che conta: la geometria è un poligono e non un punto, perché un
allagamento *ha* un'estensione e il perimetro osservato è la cosa che rende
misurabile un backtest su celle da 1 km².

Distinto da `flood_hazard` (mosaico idraulico ISPRA), che dice dove l'acqua
*può* arrivare senza dire quando: qui ci sono allagamenti accaduti.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.copernicus_ems.client import ObservationMask, ObservedFlood

log = get_logger(__name__)


async def upsert_many(items: Iterable[ObservedFlood]) -> int:
    """Insert-or-update per id, in una transazione. Rieseguibile."""
    events = list(items)
    if not events:
        return 0
    async with acquire() as conn, conn.transaction():
        for e in events:
            await conn.execute(
                """
                INSERT INTO flood_events (
                    id, source, activation_code, aoi_label, event_time,
                    observed_time, event_type, detection_method, area_km2,
                    geom, attributes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    ST_Multi(ST_SetSRID($10::geometry, 4326)), $11::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET source           = EXCLUDED.source,
                    activation_code  = EXCLUDED.activation_code,
                    aoi_label        = EXCLUDED.aoi_label,
                    event_time       = EXCLUDED.event_time,
                    observed_time    = EXCLUDED.observed_time,
                    event_type       = EXCLUDED.event_type,
                    detection_method = EXCLUDED.detection_method,
                    area_km2         = EXCLUDED.area_km2,
                    geom             = EXCLUDED.geom,
                    attributes       = EXCLUDED.attributes
                """,
                e.id,
                "copernicus-ems",
                e.activation_code,
                e.aoi_label,
                e.event_time,
                e.observed_time,
                e.event_type,
                e.detection_method,
                e.area_km2,
                e.geom,
                json.dumps(e.attributes or {}, default=str),
            )
    log.info("flood_events.upsert_many", count=len(events))
    return len(events)


async def upsert_masks(items: Iterable[ObservationMask]) -> int:
    """Scrive le maschere di osservazione. Rieseguibile."""
    masks = list(items)
    if not masks:
        return 0
    async with acquire() as conn, conn.transaction():
        for m in masks:
            await conn.execute(
                """
                INSERT INTO flood_observation_masks (
                    id, source, activation_code, aoi_label, product_type,
                    observed_time, area_km2, geom
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    ST_Multi(ST_SetSRID($8::geometry, 4326))
                )
                ON CONFLICT (id) DO UPDATE
                SET activation_code = EXCLUDED.activation_code,
                    aoi_label       = EXCLUDED.aoi_label,
                    product_type    = EXCLUDED.product_type,
                    observed_time   = EXCLUDED.observed_time,
                    area_km2        = EXCLUDED.area_km2,
                    geom            = EXCLUDED.geom
                """,
                m.id,
                "copernicus-ems",
                m.activation_code,
                m.aoi_label,
                m.product_type,
                m.observed_time,
                m.area_km2,
                m.geom,
            )
    log.info("flood_observation_masks.upsert_many", count=len(masks))
    return len(masks)


async def observation_times(aoi_id: str) -> dict[str, list[datetime]]:
    """``{cell_id: [istanti in cui la cella è stata osservata]}``.

    Il denominatore verificabile del FAR. Un'allerta su una cella che nessun
    passaggio satellitare ha coperto non è né vera né falsa, e infilarla fra i
    falsi è la ragione per cui il primo giro misurò FAR 100%.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, m.observed_time
            FROM flood_observation_masks m
            JOIN grid_cells g ON ST_Intersects(g.geom, m.geom)
            WHERE g.aoi_id = $1
            ORDER BY g.id, m.observed_time
            """,
            aoi_id,
        )
    out: dict[str, list[datetime]] = {}
    for r in rows:
        out.setdefault(str(r["cell_id"]), []).append(r["observed_time"])
    return out


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT count(*)::bigint AS n FROM flood_events")
    return int(row["n"]) if row else 0


async def truth_cells(aoi_id: str, *, start: datetime, end: datetime) -> dict[str, datetime]:
    """``{cell_id: primo event_time}`` per le celle intersecate da un allagamento.

    Il primo evento per cella è l'ancora: una cella allagata due volte nella
    finestra è **un** positivo, non due, altrimenti un'area ben allertata
    gonficerebbe l'hit rate quanto più spesso si allaga.

    ``ST_Intersects`` e non il centroide: i poligoni osservati sono spesso
    strisce lungo l'alveo, più stretti del chilometro della cella, e chiedere
    che coprano il centro scarterebbe la maggior parte degli allagamenti veri.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, min(e.event_time) AS first_event
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            WHERE g.aoi_id = $1
              AND e.event_time >= $2
              AND e.event_time <= $3
            GROUP BY g.id
            """,
            aoi_id,
            start,
            end,
        )
    return {str(r["cell_id"]): r["first_event"] for r in rows}


async def catalogue_window() -> tuple[datetime | None, datetime | None]:
    """Copertura temporale del catalogo, per il report."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT min(event_time) AS lo, max(event_time) AS hi FROM flood_events"
        )
    if row is None:
        return None, None
    return row["lo"], row["hi"]


@dataclass(frozen=True, slots=True)
class ActivationSummary:
    """Una riga di provenienza per il report."""

    activation_code: str
    event_time: datetime
    polygons: int
    area_km2: float
    name: str | None


async def activations_summary() -> list[ActivationSummary]:
    """Una riga per attivazione: data, poligoni, area. Provenienza leggibile."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT activation_code,
                   min(event_time) AS event_time,
                   count(*)        AS polygons,
                   sum(area_km2)   AS area_km2,
                   min(attributes->>'activation_name') AS name
            FROM flood_events
            GROUP BY activation_code
            ORDER BY min(event_time)
            """
        )
    return [
        ActivationSummary(
            activation_code=str(r["activation_code"]),
            event_time=r["event_time"],
            polygons=int(r["polygons"]),
            area_km2=float(r["area_km2"] or 0.0),
            name=r["name"],
        )
        for r in rows
    ]


__all__ = [
    "ActivationSummary",
    "activations_summary",
    "catalogue_window",
    "count_events",
    "observation_times",
    "truth_cells",
    "upsert_many",
    "upsert_masks",
]
