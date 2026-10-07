"""Lettura e scrittura di `pioggia_climatologia` (migrazione 065)."""

from __future__ import annotations

from dataclasses import dataclass

from limen.data.db import acquire
from limen.data.repos.fwi_state_repo import quantize


@dataclass(frozen=True, slots=True)
class NodoPioggia:
    lon: float
    lat: float
    giorni: int
    quantili: list[float]
    anno_da: int
    anno_a: int


async def upsert_many(righe: list[NodoPioggia]) -> int:
    """Scrive più nodi in un colpo. Idempotente per chiave."""
    if not righe:
        return 0
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO pioggia_climatologia (node_lon, node_lat, giorni, quantili, anno_da, anno_a)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (node_lon, node_lat) DO UPDATE SET
                giorni = EXCLUDED.giorni,
                quantili = EXCLUDED.quantili,
                anno_da = EXCLUDED.anno_da,
                anno_a = EXCLUDED.anno_a,
                computed_at = now()
            """,
            [(*quantize(r.lon, r.lat), r.giorni, r.quantili, r.anno_da, r.anno_a) for r in righe],
        )
    return len(righe)


async def nodi_fatti(anno_da: int, anno_a: int) -> set[tuple[float, float]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_lon, node_lat FROM pioggia_climatologia
            WHERE anno_da = $1 AND anno_a = $2
            """,
            anno_da,
            anno_a,
        )
    return {(float(r["node_lon"]), float(r["node_lat"])) for r in rows}


async def per_nodi(nodi: list[tuple[float, float]]) -> dict[tuple[float, float], list[float]]:
    """I quantili dei nodi richiesti che hanno una climatologia."""
    if not nodi:
        return {}
    chiavi = [quantize(lon, lat) for lon, lat in nodi]
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.node_lon, c.node_lat, c.quantili
            FROM pioggia_climatologia c
            JOIN unnest($1::numeric[], $2::numeric[]) AS n(lon, lat)
              ON c.node_lon = n.lon AND c.node_lat = n.lat
            """,
            [k[0] for k in chiavi],
            [k[1] for k in chiavi],
        )
    return {(float(r["node_lon"]), float(r["node_lat"])): list(r["quantili"]) for r in rows}
