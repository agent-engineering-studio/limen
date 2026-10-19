"""Seismic-events repository (INGV)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SeismicEvent:
    id: str
    origin_time: datetime
    magnitude: float
    magnitude_type: str | None
    depth_km: float | None
    geom: Point
    region: str | None = None
    shakemap_path: str | None = None
    raster_ref_id: int | None = None
    dataset_version_id: int | None = None
    attributes: dict[str, Any] | None = None


async def upsert_event(event: SeismicEvent) -> None:
    """Insert-or-update a seismic event by INGV eventID."""
    attrs_json = json.dumps(event.attributes or {}, default=str)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO seismic_events (
                id, origin_time, magnitude, magnitude_type, depth_km, geom, region,
                shakemap_path, raster_ref_id, dataset_version_id, attributes
            ) VALUES (
                $1, $2, $3, $4, $5, ST_SetSRID($6::geometry, 4326), $7, $8, $9, $10, $11::jsonb
            )
            ON CONFLICT (id) DO UPDATE
            SET origin_time    = EXCLUDED.origin_time,
                magnitude      = EXCLUDED.magnitude,
                magnitude_type = EXCLUDED.magnitude_type,
                depth_km       = EXCLUDED.depth_km,
                geom           = EXCLUDED.geom,
                region         = EXCLUDED.region,
                shakemap_path  = COALESCE(EXCLUDED.shakemap_path,
                                          seismic_events.shakemap_path),
                raster_ref_id  = COALESCE(EXCLUDED.raster_ref_id,
                                          seismic_events.raster_ref_id),
                dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                              seismic_events.dataset_version_id),
                attributes     = EXCLUDED.attributes,
                updated_at     = now()
            """,
            event.id,
            event.origin_time,
            event.magnitude,
            event.magnitude_type,
            event.depth_km,
            event.geom,
            event.region,
            event.shakemap_path,
            event.raster_ref_id,
            event.dataset_version_id,
            attrs_json,
        )


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM seismic_events")
    return int(row["n"]) if row else 0


async def get_event(event_id: str) -> SeismicEvent | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, origin_time, magnitude, magnitude_type, depth_km, geom,
                   region, shakemap_path, raster_ref_id, dataset_version_id, attributes
            FROM seismic_events WHERE id = $1
            """,
            event_id,
        )
    if row is None:
        return None
    attrs = row["attributes"]
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    return SeismicEvent(
        id=str(row["id"]),
        origin_time=row["origin_time"],
        magnitude=float(row["magnitude"]),
        magnitude_type=row["magnitude_type"],
        depth_km=float(row["depth_km"]) if row["depth_km"] is not None else None,
        geom=row["geom"],
        region=row["region"],
        shakemap_path=row["shakemap_path"],
        raster_ref_id=row["raster_ref_id"],
        dataset_version_id=row["dataset_version_id"],
        attributes=attrs or {},
    )


async def celle_nel_riquadro(
    ovest: float, sud: float, est: float, nord: float
) -> list[tuple[str, float, float]]:
    """(cell_id, lon, lat del centroide) delle celle dentro il riquadro di una ShakeMap."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_X(centroid) AS lon, ST_Y(centroid) AS lat
              FROM grid_cells
             WHERE centroid && ST_MakeEnvelope($1, $2, $3, $4, 4326)
            """,
            ovest,
            sud,
            est,
            nord,
        )
    return [(r["id"], float(r["lon"]), float(r["lat"])) for r in rows]


async def salva_pga_celle(event_id: str, pga: list[tuple[str, float]]) -> int:
    """Sostituisce lo scuotimento per cella di un evento (#284).

    Sostituisce e non aggiunge: una ShakeMap rivista nelle ore dopo il
    terremoto può restringere l'area, e le celle che ne escono non devono
    restare scosse.
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM seismic_pga_cella WHERE event_id = $1", event_id)
        if pga:
            await conn.executemany(
                "INSERT INTO seismic_pga_cella (event_id, cell_id, pga_g) VALUES ($1, $2, $3)",
                [(event_id, cella, valore) for cella, valore in pga],
            )
        await conn.execute("UPDATE seismic_events SET pga_celle_at = now() WHERE id = $1", event_id)
    return len(pga)


async def pga_celle_calcolata(event_id: str) -> bool:
    """Se la PGA per cella di questo evento è già stata calcolata (#284)."""
    async with acquire() as conn:
        return bool(
            await conn.fetchval(
                "SELECT pga_celle_at IS NOT NULL FROM seismic_events WHERE id = $1", event_id
            )
        )


@dataclass(frozen=True, slots=True)
class ScossaCella:
    cell_id: str
    event_id: str
    origin_time: datetime
    magnitude: float
    pga_g: float
    distanza_km: float


async def scosse_per_cella(
    cell_ids: list[str], dal: datetime, al: datetime, *, min_magnitude: float
) -> list[ScossaCella]:
    """I terremoti della finestra che hanno scosso queste celle, con la PGA di ognuna."""
    if not cell_ids:
        return []
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.cell_id, e.id, e.origin_time, e.magnitude, p.pga_g,
                   ST_Distance(e.geom::geography, c.centroid::geography) / 1000.0
                       AS distanza_km
              FROM seismic_pga_cella p
              JOIN seismic_events e ON e.id = p.event_id
              JOIN grid_cells c ON c.id = p.cell_id
             WHERE p.cell_id = ANY($1::text[])
               AND e.origin_time BETWEEN $2 AND $3
               AND e.magnitude >= $4
            """,
            cell_ids,
            dal,
            al,
            min_magnitude,
        )
    return [
        ScossaCella(
            cell_id=r["cell_id"],
            event_id=r["id"],
            origin_time=r["origin_time"],
            magnitude=float(r["magnitude"]),
            pga_g=float(r["pga_g"]),
            distanza_km=float(r["distanza_km"]),
        )
        for r in rows
    ]
