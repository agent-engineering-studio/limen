"""Persistence of the recursive FWI chain (issue #61).

Keyed by **weather node**, not by cell: the chain is a function of the
weather alone, and Open-Meteo serves it at ~9 km, so the tens of thousands of
cells in a region share a few dozen chains. Storing one copy per cell would
duplicate the same six numbers ~500 times a day for nothing.

Three operations, and the asymmetry is the point: reading the latest state
**before** a day is what every advance starts with, reading a whole day's grid
is what a sweep needs, and writing is an upsert because re-running a day must
not fork the chain.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from limen.core.logging import get_logger
from limen.core.models.risk import FireWeatherState
from limen.core.scoring.wildfire.fwi import FwiOutputs, FwiState
from limen.data.db import acquire

log = get_logger(__name__)

#: The PK is NUMERIC(9,4), so a node is addressed at exactly this precision.
#: Rounding here rather than trusting the caller keeps a 0.25° grid built from
#: a float accumulator ("41.099999999999994") from opening a second chain
#: alongside the one it means to extend.
_QUANT = Decimal("0.0001")


def quantize(lon: float, lat: float) -> tuple[Decimal, Decimal]:
    """A node's key, at the precision the table stores."""
    return (
        Decimal(repr(lon)).quantize(_QUANT),
        Decimal(repr(lat)).quantize(_QUANT),
    )


@dataclass(frozen=True, slots=True)
class StoredChain:
    """A node's chain as of one day."""

    day: date
    state: FwiState
    chain_days: int


@dataclass(frozen=True, slots=True)
class NodeDay:
    """One node's computed day, ready to be written."""

    lon: float
    lat: float
    day: date
    outputs: FwiOutputs
    chain_days: int
    temperature_c: float
    relative_humidity_pct: float
    wind_speed_kmh: float
    rain_24h_mm: float


async def latest_before(lon: float, lat: float, day: date) -> StoredChain | None:
    """The most recent state strictly before ``day``, or ``None``.

    Strictly before, so re-running a day rebuilds it from its true
    predecessor instead of from itself.
    """
    node_lon, node_lat = quantize(lon, lat)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT day, ffmc, dmc, dc, chain_days
              FROM fwi_state
             WHERE node_lon = $1 AND node_lat = $2 AND day < $3
             ORDER BY day DESC
             LIMIT 1
            """,
            node_lon,
            node_lat,
            day,
        )
    if row is None:
        return None
    return StoredChain(
        day=row["day"],
        state=FwiState(ffmc=row["ffmc"], dmc=row["dmc"], dc=row["dc"]),
        chain_days=int(row["chain_days"]),
    )


async def read_day(nodes: list[tuple[float, float]], day: date) -> list[FireWeatherState | None]:
    """The stored chain of each node on ``day``, in the order given.

    One query for the whole grid: a sweep resolves every cell's fire weather
    from this, and per-node round trips would put a few hundred queries in
    front of every hourly tick.
    """
    keys = [quantize(lon, lat) for lon, lat in nodes]
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_lon, node_lat, day, ffmc, dmc, dc, isi, bui, fwi, chain_days
              FROM fwi_state
             WHERE day = $1
               AND (node_lon, node_lat) IN (
                   SELECT unnest($2::numeric[]), unnest($3::numeric[])
               )
            """,
            day,
            [k[0] for k in keys],
            [k[1] for k in keys],
        )
    by_key = {
        (r["node_lon"], r["node_lat"]): FireWeatherState(
            day=r["day"],
            ffmc=r["ffmc"],
            dmc=r["dmc"],
            dc=r["dc"],
            isi=r["isi"],
            bui=r["bui"],
            fwi=r["fwi"],
            chain_days=int(r["chain_days"]),
        )
        for r in rows
    }
    return [by_key.get(k) for k in keys]


async def upsert_many(days: list[NodeDay]) -> int:
    """Write many node-days in one round trip. Idempotent per (node, day)."""
    if not days:
        return 0
    records = [
        (
            *quantize(d.lon, d.lat),
            d.day,
            d.outputs.state.ffmc,
            d.outputs.state.dmc,
            d.outputs.state.dc,
            d.outputs.isi,
            d.outputs.bui,
            d.outputs.fwi,
            d.chain_days,
            d.temperature_c,
            d.relative_humidity_pct,
            d.wind_speed_kmh,
            d.rain_24h_mm,
        )
        for d in days
    ]
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO fwi_state (
                node_lon, node_lat, day, ffmc, dmc, dc, isi, bui, fwi, chain_days,
                temperature_c, relative_humidity_pct, wind_speed_kmh, rain_24h_mm
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (node_lon, node_lat, day) DO UPDATE SET
                ffmc = EXCLUDED.ffmc,
                dmc = EXCLUDED.dmc,
                dc = EXCLUDED.dc,
                isi = EXCLUDED.isi,
                bui = EXCLUDED.bui,
                fwi = EXCLUDED.fwi,
                chain_days = EXCLUDED.chain_days,
                temperature_c = EXCLUDED.temperature_c,
                relative_humidity_pct = EXCLUDED.relative_humidity_pct,
                wind_speed_kmh = EXCLUDED.wind_speed_kmh,
                rain_24h_mm = EXCLUDED.rain_24h_mm,
                computed_at = now()
            """,
            records,
        )
    return len(records)


__all__ = ["NodeDay", "StoredChain", "latest_before", "quantize", "read_day", "upsert_many"]
