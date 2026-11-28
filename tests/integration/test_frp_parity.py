"""The FRP refresh through limen-core gives what the SQL gave (#714).

`refresh_perimeter_frp` was one SQL statement; now the rule lives in
`limen_core.wildfire.seen_inside_all` and Limen only reads and writes. This
runs both on the same rows, on the cases where two implementations of "inside
the perimeter, around its day" can disagree: a point on the edge, on a
vertex, in a hole, the last day of the window and the first day out, a
second part of a MultiPolygon, a perimeter with no area, one with no date,
and detections that do not count (another type, no power).
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from limen.data.db import acquire
from limen.data.repos.fire_events_repo import (
    _REFRESH_FRP_SQL_LEGACY,
    FRP_WINDOW_DAYS,
    refresh_perimeter_frp,
)
from limen.data.repos.fire_repo import FireHotspot, upsert_hotspots

pytestmark = pytest.mark.integration

DAY = dt.date(2025, 7, 20)
SQUARE = "ST_Multi(ST_MakeEnvelope(16.0, 41.0, 16.1, 41.1, 4326))"
HOLED = (
    "ST_Multi(ST_GeomFromText('POLYGON((15.0 40.0, 15.2 40.0, 15.2 40.2, 15.0 40.2, 15.0 40.0),"
    "(15.05 40.05, 15.15 40.05, 15.15 40.15, 15.05 40.15, 15.05 40.05))', 4326))"
)
TWO_PARTS = (
    "ST_GeomFromText('MULTIPOLYGON(((17.0 39.0, 17.1 39.0, 17.1 39.1, 17.0 39.1, 17.0 39.0)),"
    "((17.3 39.0, 17.4 39.0, 17.4 39.1, 17.3 39.1, 17.3 39.0)))', 4326)"
)

PERIMETERS = [
    ("square", DAY, 100.0, SQUARE),
    ("holed", DAY, 300.0, HOLED),
    ("two-parts", DAY, 200.0, TWO_PARTS),
    ("no-area", DAY, None, "ST_Multi(ST_MakeEnvelope(14.0, 38.0, 14.1, 38.1, 4326))"),
    ("zero-area", DAY, 0.0, "ST_Multi(ST_MakeEnvelope(14.5, 38.0, 14.6, 38.1, 4326))"),
    ("no-date", None, 50.0, "ST_Multi(ST_MakeEnvelope(13.0, 37.0, 13.1, 37.1, 4326))"),
    ("nothing-seen", DAY, 80.0, "ST_Multi(ST_MakeEnvelope(12.0, 42.0, 12.1, 42.1, 4326))"),
]


def spot(
    lon: float,
    lat: float,
    *,
    day: dt.date = DAY,
    frp: float | None = 10.0,
    kind: int | None = 0,
    t: int = 1200,
) -> FireHotspot:
    return FireHotspot(
        source="TEST",
        acq_date=day,
        acq_time=t,
        latitude=lat,
        longitude=lon,
        frp_mw=frp,
        detection_type=kind,
    )


W = dt.timedelta(days=FRP_WINDOW_DAYS)
HOTSPOTS = [
    spot(16.05, 41.05, frp=12.0),  # inside
    spot(16.1, 41.05, frp=3.0, t=1201),  # on the east edge
    spot(16.0, 41.0, frp=2.0, t=1202),  # on a vertex
    spot(16.05, 41.05, day=DAY + W, frp=4.0, t=1203),  # last day of the window
    spot(16.05, 41.05, day=DAY - W, frp=5.0, t=1204),  # first day of the window
    spot(16.05, 41.05, day=DAY + W + dt.timedelta(days=1), frp=99.0),  # a day out
    spot(16.05, 41.05, kind=2, frp=500.0, t=1205),  # a steelworks
    spot(16.05, 41.05, frp=None, t=1206),  # no power
    spot(16.11, 41.05, frp=77.0, t=1207),  # just outside
    spot(15.1, 40.1, frp=40.0),  # in the hole
    spot(15.02, 40.1, frp=6.0),  # in the ring around the hole
    spot(15.05, 40.1, frp=7.0, t=1208),  # on the edge of the hole
    spot(17.05, 39.05, frp=8.0),  # first part
    spot(17.35, 39.05, frp=9.0),  # second part
    spot(17.2, 39.05, frp=88.0),  # between the parts
    spot(14.05, 38.05, frp=11.0),  # no area
    spot(14.55, 38.05, frp=13.0),  # zero area
    spot(13.05, 37.05, frp=14.0),  # no date
]


async def _seed() -> None:
    async with acquire() as conn:
        for pid, day, area, geom in PERIMETERS:
            await conn.execute(
                "INSERT INTO fire_perimeters (layer, id, fire_date, area_ha, geom) "
                f"VALUES ('ms:modis.ba.poly', $1, $2, $3, {geom})",
                pid,
                day,
                area,
            )
        # A perimeter of the other layer, on the same place: never touched.
        await conn.execute(
            "INSERT INTO fire_perimeters (layer, id, fire_date, area_ha, geom) "
            f"VALUES ('nrt.ba.poly', 'square', $1, 100, {SQUARE})",
            DAY,
        )
    await upsert_hotspots(HOTSPOTS)


async def _read() -> dict[str, tuple[float | None, int | None, float | None]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, frp_sum_mw, frp_hotspots, frp_density_mw_per_ha FROM v_fire_perimeters"
        )
    return {r["id"]: (r["frp_sum_mw"], r["frp_hotspots"], r["frp_density_mw_per_ha"]) for r in rows}


def _same(a: tuple[float | None, ...], b: tuple[float | None, ...]) -> bool:
    return all(
        (x is None and y is None)
        or (x is not None and y is not None and math.isclose(x, y, rel_tol=1e-12))
        for x, y in zip(a, b, strict=True)
    )


async def test_limen_core_gives_what_the_sql_gave(reset_db: None) -> None:
    await _seed()
    async with acquire() as conn:
        await conn.execute(_REFRESH_FRP_SQL_LEGACY, FRP_WINDOW_DAYS)
    legacy = await _read()
    async with acquire() as conn:
        await conn.execute(
            "UPDATE fire_perimeters SET frp_sum_mw = NULL, frp_hotspots = NULL, "
            "frp_density_mw_per_ha = NULL"
        )
    measured = await refresh_perimeter_frp()
    core = await _read()

    assert set(core) == set(legacy)
    differ = {pid: (legacy[pid], core[pid]) for pid in core if not _same(legacy[pid], core[pid])}
    assert differ == {}
    # The cases themselves, so that a shared mistake is not a parity.
    assert core["square"] == (26.0, 5, 0.26)  # inside, edge, vertex, both window ends
    assert core["holed"] == (13.0, 2, 13.0 / 300)  # ring and the hole's edge, not the hole
    assert core["two-parts"] == (17.0, 2, 17.0 / 200)
    assert core["no-area"] == (11.0, 1, None)
    assert core["zero-area"] == (13.0, 1, None)
    assert core["no-date"] == (None, None, None)
    assert core["nothing-seen"] == (None, None, None)
    assert measured == 5


async def test_the_other_layer_is_not_touched(reset_db: None) -> None:
    await _seed()
    await refresh_perimeter_frp()
    async with acquire() as conn:
        other = await conn.fetchrow(
            "SELECT frp_sum_mw FROM fire_perimeters WHERE layer = 'nrt.ba.poly' AND id = 'square'"
        )
    assert other is not None and other["frp_sum_mw"] is None


async def test_a_second_run_writes_nothing(reset_db: None) -> None:
    await _seed()
    await refresh_perimeter_frp()
    async with acquire() as conn:
        before = await conn.fetchval("SELECT max(updated_at) FROM fire_perimeters")
    await refresh_perimeter_frp()
    async with acquire() as conn:
        after = await conn.fetchval("SELECT max(updated_at) FROM fire_perimeters")
    assert after == before


async def test_a_perimeter_no_longer_seen_goes_back_to_not_measured(reset_db: None) -> None:
    """The SQL left an old value where no detection counted any more; this clears it."""
    await _seed()
    await refresh_perimeter_frp()
    async with acquire() as conn:
        await conn.execute("DELETE FROM fire_hotspots WHERE latitude = 38.05")
    await refresh_perimeter_frp()
    assert (await _read())["no-area"] == (None, None, None)
