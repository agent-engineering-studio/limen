"""Lettura e scrittura di `fwi_climatology` (migrazione 061)."""

from __future__ import annotations

from dataclasses import dataclass

from limen.core.scoring.regional_thresholds import TettoPerNodoBlock
from limen.core.scoring.wildfire.climatology import tetto_del_nodo
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


async def per_punto(lon: float, lat: float, month: int, raggio: float) -> NodoMese | None:
    """Il nodo di (lon, lat) per quel mese, o ``None``.

    ``raggio`` è la distanza massima, in gradi, dal nodo che la catena
    operativa assegnerebbe al punto (metà diagonale del passo del reticolo).
    Più largo, un nodo mancante verrebbe sostituito in silenzio da uno a
    decine di chilometri, presentato come «questo punto».
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT node_lon, node_lat, month, days, quantiles, year_from, year_to
            FROM fwi_climatology
            WHERE month = $3
              AND node_lon::float8 BETWEEN $1::float8 - 0.5 AND $1::float8 + 0.5
              AND node_lat::float8 BETWEEN $2::float8 - 0.5 AND $2::float8 + 0.5
              AND (node_lon::float8 - $1::float8) ^ 2 + (node_lat::float8 - $2::float8) ^ 2
                  <= $4::float8 ^ 2
            ORDER BY (node_lon::float8 - $1::float8) ^ 2 + (node_lat::float8 - $2::float8) ^ 2
            LIMIT 1
            """,
            lon,
            lat,
            month,
            raggio,
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


async def per_nodi(
    nodi: list[tuple[float, float]], mesi: tuple[int, ...]
) -> dict[tuple[float, float], dict[int, list[float]]]:
    """I quantili di ``mesi`` per ogni nodo, con le coordinate quantizzate come la tabella."""
    if not nodi:
        return {}
    chiavi = [quantize(lon, lat) for lon, lat in nodi]
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.node_lon, c.node_lat, c.month, c.quantiles
            FROM fwi_climatology c
            JOIN unnest($1::numeric[], $2::numeric[]) AS n(lon, lat)
              ON c.node_lon = n.lon AND c.node_lat = n.lat
            WHERE c.month = ANY($3::smallint[])
            """,
            [k[0] for k in chiavi],
            [k[1] for k in chiavi],
            list(mesi),
        )
    out: dict[tuple[float, float], dict[int, list[float]]] = {}
    for r in rows:
        out.setdefault((float(r["node_lon"]), float(r["node_lat"])), {})[int(r["month"])] = list(
            r["quantiles"]
        )
    return out


async def tetti(
    nodi: list[tuple[float, float]], blocco: TettoPerNodoBlock, massimo: float
) -> list[float | None]:
    """Il FWI pieno di ogni nodo (#476), allineato a ``nodi``; ``None`` senza climatologia."""
    per_nodo = await per_nodi(nodi, blocco.mesi)
    out: list[float | None] = []
    for lon, lat in nodi:
        q = quantize(lon, lat)
        out.append(tetto_del_nodo(per_nodo.get((float(q[0]), float(q[1])), {}), blocco, massimo))
    return out
