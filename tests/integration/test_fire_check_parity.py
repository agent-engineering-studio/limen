"""The post-fire decision through limen-core gives what the SQL gave (#714).

`FireCheckExecutor` took its decision inside one query; now the query only
reads, and `limen_core.wildfire.latest_fire` decides. This runs the old query
and the old loop (frozen here) next to the executor on the same rows: random
perimeters and FIRMS days over a real grid, with dates in the future, past the
window, on unconfirmed days, and perimeters with no density.
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from shapely.geometry import MultiPolygon, box

from limen.agents.executors.fire_check import _LEGACY_QUERY_SQL, FireCheckExecutor
from limen.core.models.context import MonitoringContext
from limen.core.scoring.post_fire import frp_severity
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.fire_repo import FireHotspot, upsert_hotspots
from limen.data.repos.grid_repo import generate_and_store_grid

pytestmark = pytest.mark.integration

AOI = "fire-check-parity"
BOUNDS = (16.0, 40.0, 16.1, 40.06)
NOW = datetime(2026, 11, 28, 12, tzinfo=UTC)


def legacy_loop(rows: list[Any], *, oggi: date) -> dict[str, tuple[float, float | None]]:
    """The loop of `FireCheckExecutor.run` at Limen 46c2a5b, as it was."""
    post_fire = load_regional_thresholds().post_fire
    per_cella: dict[str, tuple[float, float | None]] = {}
    for r in rows:
        date_note = [d for d in (r["data_perimetro"], r["data_punti"]) if d is not None]
        ultima = max(date_note)
        mesi = max(0.0, (oggi - ultima).days / 30.0)
        if mesi > post_fire.window_months_max:
            continue
        densita = r["densita"] if r["data_perimetro"] == ultima else None
        per_cella[r["cell_id"]] = (
            mesi,
            frp_severity(densita, post_fire=post_fire) if densita is not None else None,
        )
    return per_cella


async def _seed(rng: random.Random) -> None:
    await upsert_aoi(
        id=AOI, name="parity", kind="region", geom=MultiPolygon([box(*BOUNDS)]), metadata={}
    )
    await generate_and_store_grid(AOI)
    today = NOW.date()
    days = [today - timedelta(days=rng.randint(-4, 800)) for _ in range(30)]
    # Every perimeter on its own day: where two of one day touch a cell the
    # old SQL took either, and limen-core the denser (the test below).
    perimeter_days = rng.sample(range(-4, 800), 40)
    async with acquire() as conn:
        for i, back in enumerate(perimeter_days):
            west = rng.uniform(15.99, 16.09)
            south = rng.uniform(39.99, 40.05)
            await conn.execute(
                "INSERT INTO fire_perimeters (layer, id, fire_date, area_ha, geom, "
                "frp_density_mw_per_ha) VALUES ('ms:modis.ba.poly', $1, $2, 50, "
                "ST_Multi(ST_MakeEnvelope($3, $4, $5, $6, 4326)), $7)",
                f"p{i}",
                today - timedelta(days=back),
                west,
                south,
                west + rng.uniform(0.002, 0.03),
                south + rng.uniform(0.002, 0.02),
                None if rng.random() < 0.2 else rng.uniform(0.0, 3.0),
            )
    await upsert_hotspots(
        [
            FireHotspot(
                source="TEST",
                acq_date=rng.choice(days),
                acq_time=1000 + k // 60 * 100 + k % 60,
                latitude=rng.uniform(39.99, 40.07),
                longitude=rng.uniform(15.99, 16.11),
                detection_type=rng.choice([0, 0, 0, 2, None]),
            )
            for k in range(120)
        ]
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("min_hotspots", [1, 3])
async def test_limen_core_gives_what_the_query_gave(
    reset_db: None, pg_pool: object, seed: int, min_hotspots: int
) -> None:
    await _seed(random.Random(seed))
    post_fire = load_regional_thresholds().post_fire
    today = NOW.date()
    oldest = today - timedelta(days=post_fire.window_months_max * 30.44)
    async with acquire() as conn:
        rows = await conn.fetch(_LEGACY_QUERY_SQL, AOI, min_hotspots, oldest, today)
    expected = legacy_loop(rows, oggi=today)

    ctx = MonitoringContext(aoi_id=AOI, valuation_time=NOW)
    got = await FireCheckExecutor(min_hotspots=min_hotspots).run(ctx)

    assert got.fuoco_per_cella == expected
    assert expected, "the scenario must burn some cells"


async def test_two_perimeters_of_one_day_read_the_denser(reset_db: None, pg_pool: object) -> None:
    """The one deliberate difference: the old `DISTINCT ON` took either one."""
    await upsert_aoi(
        id=AOI, name="parity", kind="region", geom=MultiPolygon([box(*BOUNDS)]), metadata={}
    )
    await generate_and_store_grid(AOI)
    day = NOW.date() - timedelta(days=30)
    async with acquire() as conn:
        for pid, density in (("weak", 0.1), ("strong", 1.5)):
            await conn.execute(
                "INSERT INTO fire_perimeters (layer, id, fire_date, area_ha, geom, "
                "frp_density_mw_per_ha) VALUES ('ms:modis.ba.poly', $1, $2, 50, "
                "ST_Multi(ST_MakeEnvelope(15.99, 39.99, 16.11, 40.07, 4326)), $3)",
                pid,
                day,
                density,
            )
    post_fire = load_regional_thresholds().post_fire
    got = await FireCheckExecutor(min_hotspots=3).run(
        MonitoringContext(aoi_id=AOI, valuation_time=NOW)
    )
    assert got.fuoco_per_cella
    assert set(got.fuoco_per_cella.values()) == {(1.0, frp_severity(1.5, post_fire=post_fire))}
