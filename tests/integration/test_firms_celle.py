"""``firms_client.cell_stats`` sulla griglia di Limen (#714, fase 4 di firms-client#26).

Due cose: la griglia ricostruita dalla libreria è quella del database (i
giorni-incendio per cella coincidono con ``fire_density``), e la quota di
coltivi arriva in ``crop_burning_share`` con NULL dove non c'è fuoco.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Any

import pytest

from limen.data.db import acquire
from limen.data.repos.fire_events_repo import rebuild_events, refresh_density
from limen.data.repos.fire_repo import FireHotspot, upsert_hotspots
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.integrations.firms import celle

pytestmark = pytest.mark.integration

AOI = "bt-firms-celle"
WINDOW = (dt.date(2024, 1, 1), dt.date(2024, 12, 31))


async def _seed() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT celle','region',"
            "ST_Multi(ST_MakeEnvelope(16.0, 40.9, 16.06, 40.95, 4326)))",
            AOI,
        )
    await generate_and_store_grid(AOI)
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO cell_static_factors (cell_id) SELECT id FROM grid_cells WHERE aoi_id=$1",
            AOI,
        )


def _hotspots(n: int) -> list[FireHotspot]:
    rng = random.Random(11)
    return [
        FireHotspot(
            source="VIIRS_SNPP_SP",
            acq_date=dt.date(2024, 7, rng.randint(1, 5)),
            acq_time=rng.choice((130, 1230)),
            latitude=rng.uniform(40.9, 40.95),
            longitude=rng.uniform(16.0, 16.06),
            frp_mw=5.0,
            confidence="n",
            brightness_k=330.0,
            daynight="D",
            satellite="N",
            instrument="VIIRS",
            detection_type=0,
        )
        for _ in range(n)
    ]


class _Terra:
    """Coltivi a est di 16.03, bosco a ovest."""

    def shares(self, latitude: float, longitude: float, radius_m: float) -> dict[int, float]:
        return {40: 1.0} if longitude > 16.03 else {10: 1.0}

    def __enter__(self) -> _Terra:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


async def test_the_library_grid_is_limen_grid(reset_db: None, pg_pool: object) -> None:
    await _seed()
    await upsert_hotspots(_hotspots(300))
    await rebuild_events(start=WINDOW[0], end=WINDOW[1])
    await refresh_density(AOI, start=WINDOW[0], end=WINDOW[1])
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT c.cell_id, c.fire_density FROM cell_static_factors c "
            "JOIN grid_cells g ON g.id = c.cell_id WHERE g.aoi_id = $1",
            AOI,
        )
    sql = {r["cell_id"]: r["fire_density"] for r in rows}

    from firms_client import cell_stats

    grid = await celle.griglia(AOI)
    stats = cell_stats(await celle.rilevazioni(AOI, dal=WINDOW[0]), grid, cells=[])
    libreria = {celle.id_cella(AOI, c): s.fire_days for c, s in stats.items()}

    assert sum(1 for v in sql.values() if v) > 10
    assert {k: v for k, v in sql.items() if v} == {
        k: v for k, v in libreria.items() if k in sql and v
    }
    assert set(libreria) <= set(sql)


async def test_crop_share_is_written_and_null_where_nothing_burnt(
    reset_db: None, pg_pool: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed()
    await upsert_hotspots(_hotspots(60))
    terra: Any = _Terra()
    monkeypatch.setattr(celle, "worldcover_locale", lambda: terra)

    misurate = await celle.aggiorna_quota_coltivi(AOI)

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT c.crop_burning_share AS q FROM cell_static_factors c "
            "JOIN grid_cells g ON g.id = c.cell_id WHERE g.aoi_id = $1",
            AOI,
        )
    valori = [r["q"] for r in rows]
    assert misurate == sum(v is not None for v in valori) > 0
    assert {v for v in valori if v is not None} <= {0.0, 1.0}
    assert any(v is None for v in valori)  # niente fuoco: non misurato, non zero


async def test_without_worldcover_the_step_writes_nothing(
    reset_db: None, pg_pool: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed()
    monkeypatch.setattr(celle, "worldcover_locale", lambda: None)
    assert await celle.aggiorna_quota_coltivi(AOI) == 0


async def test_a_grid_that_does_not_match_is_refused(reset_db: None, pg_pool: object) -> None:
    """Celle salvate con indici che la griglia ricostruita non riproduce: niente scrittura."""
    await _seed()
    async with acquire() as conn:
        await conn.execute("UPDATE grid_cells SET col_idx = 100 - col_idx WHERE aoi_id = $1", AOI)
    with pytest.raises(celle.GrigliaDiversaError):
        await celle.griglia(AOI)
