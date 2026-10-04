"""Lettura e scrittura di `fwi_climatology` (migrazione 061)."""

from __future__ import annotations

from dataclasses import dataclass

from limen.data.db import acquire
from limen.data.repos.fwi_state_repo import quantize


@dataclass(frozen=True, slots=True)
class NodoMese:
    lon: float
    lat: float
    month: int
    days: int
    quantiles: list[float]
    year_from: int
    year_to: int


async def upsert_many(righe: list[NodoMese]) -> int:
    """Scrive più (nodo, mese) in un colpo. Idempotente per chiave."""
    if not righe:
        return 0
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO fwi_climatology (
                node_lon, node_lat, month, days, quantiles, year_from, year_to
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (node_lon, node_lat, month) DO UPDATE SET
                days = EXCLUDED.days,
                quantiles = EXCLUDED.quantiles,
                year_from = EXCLUDED.year_from,
                year_to = EXCLUDED.year_to,
                computed_at = now()
            """,
            [
                (*quantize(r.lon, r.lat), r.month, r.days, r.quantiles, r.year_from, r.year_to)
                for r in righe
            ],
        )
    return len(righe)


async def nodi_fatti(year_from: int, year_to: int) -> set[tuple[float, float]]:
    """I nodi che hanno già tutti e dodici i mesi per questo intervallo di anni."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_lon, node_lat FROM fwi_climatology
            WHERE year_from = $1 AND year_to = $2
            GROUP BY node_lon, node_lat HAVING count(*) = 12
            """,
            year_from,
            year_to,
        )
    return {(float(r["node_lon"]), float(r["node_lat"])) for r in rows}


async def per_punto(lon: float, lat: float, month: int) -> NodoMese | None:
    """Il nodo più vicino a (lon, lat) per quel mese, entro mezzo grado."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT node_lon, node_lat, month, days, quantiles, year_from, year_to
            FROM fwi_climatology
            WHERE month = $3
              AND node_lon::float8 BETWEEN $1::float8 - 0.5 AND $1::float8 + 0.5
              AND node_lat::float8 BETWEEN $2::float8 - 0.5 AND $2::float8 + 0.5
            ORDER BY (node_lon::float8 - $1::float8) ^ 2 + (node_lat::float8 - $2::float8) ^ 2
            LIMIT 1
            """,
            lon,
            lat,
            month,
        )
    if row is None:
        return None
    return NodoMese(
        lon=float(row["node_lon"]),
        lat=float(row["node_lat"]),
        month=int(row["month"]),
        days=int(row["days"]),
        quantiles=[float(v) for v in row["quantiles"]],
        year_from=int(row["year_from"]),
        year_to=int(row["year_to"]),
    )
