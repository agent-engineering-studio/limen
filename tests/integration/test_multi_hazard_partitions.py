"""Hazard dimension + daily partitioning of the hot tables (issue #82).

The assertions that matter here are the ones protecting the public map: with a
single hazard enabled, `v_region_tiles` and `mv_comune_risk` must report the
same per-cell counts they reported before the hazard column existed. Enabling
a second hazard multiplies `mv_latest_risk` rows, and any consumer that
forgot to filter would silently double-count.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire
from limen.data.repos import partitions_repo
from limen.data.repos.alert_dispatches_repo import (
    AlertDispatchRow,
    cells_dispatched_within,
)
from limen.data.repos.alert_dispatches_repo import insert_many as insert_dispatches
from limen.data.repos.map_views_repo import refresh_latest_risk

pytestmark = pytest.mark.integration

_AOI_ID = "hz-test-aoi"
_CELLS = ("hz-cell-1", "hz-cell-2", "hz-cell-3")


async def _seed_cells(conn: asyncpg.Connection) -> None:
    """One AOI and three small cells, enough for the view arithmetic."""
    await conn.execute(
        """
        INSERT INTO aoi (id, name, kind, geom)
        VALUES ($1, 'Hazard test', 'region',
                ST_Multi(ST_MakeEnvelope(16.8, 41.1, 16.9, 41.2, 4326)))
        ON CONFLICT (id) DO NOTHING
        """,
        _AOI_ID,
    )
    for i, cell_id in enumerate(_CELLS):
        lon = 16.81 + i * 0.01
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 0, $3,
                    ST_MakeEnvelope($4::float8, 41.11, $4::float8 + 0.01, 41.12, 4326),
                    1.0)
            ON CONFLICT (id) DO NOTHING
            """,
            cell_id,
            _AOI_ID,
            i,
            lon,
        )


async def _force_refresh() -> None:
    """Refresh past the 5-minute debounce, which a test cannot wait out."""
    async with acquire() as conn:
        await conn.execute("UPDATE mv_refresh_state SET refreshed_at = 'epoch'::timestamptz")
    await refresh_latest_risk()


async def _insert_assessment(
    conn: asyncpg.Connection,
    cell_id: str,
    *,
    hazard: HazardType,
    score: float,
    level: str,
    computed_at: datetime | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO risk_assessments (
            cell_id, computed_at, hazard_type, horizon, score, class,
            factors, pipeline_version
        ) VALUES ($1, COALESCE($2, now()), $3, '24h', $4, $5,
                  jsonb_build_object('e', 0.5), 'test')
        """,
        cell_id,
        computed_at,
        hazard.value,
        score,
        level,
    )


@pytest.fixture()
async def hazard_fixture(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await conn.execute("TRUNCATE alert_dispatches, forecast_dispatches")
        await conn.execute("UPDATE hazards SET enabled = (hazard = 'landslide')")
        await _seed_cells(conn)
    yield
    # `hazards` is not in reset_db, and one test enables flood: without this
    # teardown every later test in the session would see a two-hazard view.
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = (hazard = 'landslide')")
    await _force_refresh()


async def test_hot_tables_are_partitioned_by_day(hazard_fixture: None) -> None:
    async with acquire() as conn:
        for table in partitions_repo.PARTITIONED_TABLES:
            key = await conn.fetchval("SELECT pg_get_partkeydef($1::regclass)", f"public.{table}")
            assert key == "RANGE (computed_at)"
        # Today's partition has to exist before a sweep writes into it.
        today = datetime.now(UTC).strftime("%Y%m%d")
        exists = await conn.fetchval(
            "SELECT count(*) FROM pg_class WHERE relname = $1",
            f"risk_assessments_{today}",
        )
        assert exists == 1

    # A write must land in a dated partition, never in DEFAULT: retention only
    # drops dated ones, so rows in DEFAULT would never expire.
    async with acquire() as conn:
        await _insert_assessment(
            conn, _CELLS[0], hazard=DEFAULT_HAZARD, score=0.4, level="Moderate"
        )
    assert await partitions_repo.default_partition_rows("risk_assessments") == 0


async def test_ensure_partitions_is_idempotent(hazard_fixture: None) -> None:
    await partitions_repo.ensure(days_ahead=3)
    again = await partitions_repo.ensure(days_ahead=3)
    assert all(count == 0 for count in again.values())


async def test_drop_expired_partitions_honours_retention(hazard_fixture: None) -> None:
    old_day = (datetime.now(UTC) - timedelta(days=40)).date()
    part = f"risk_assessments_{old_day.strftime('%Y%m%d')}"
    async with acquire() as conn:
        await conn.fetchval(
            "SELECT ensure_partitions('risk_assessments', $1::date, $1::date)", old_day
        )
        await _insert_assessment(
            conn,
            _CELLS[0],
            hazard=DEFAULT_HAZARD,
            score=0.4,
            level="Moderate",
            computed_at=datetime.combine(old_day, datetime.min.time(), tzinfo=UTC),
        )
        # `part` is built from a date we just formatted, not from input.
        assert await conn.fetchval(f"SELECT count(*) FROM ONLY {part}") == 1

    # 0 means "keep everything", the documented escape hatch.
    assert await partitions_repo.drop_expired("risk_assessments", 0) == 0
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM pg_class WHERE relname = $1", part) == 1

    assert await partitions_repo.drop_expired("risk_assessments", 14) >= 1
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM pg_class WHERE relname = $1", part) == 0


async def test_latest_view_keys_on_cell_and_hazard(hazard_fixture: None) -> None:
    async with acquire() as conn:
        await _insert_assessment(
            conn, _CELLS[0], hazard=DEFAULT_HAZARD, score=0.9, level="VeryHigh"
        )
    await _force_refresh()

    async with acquire() as conn:
        total, distinct = await conn.fetchrow(
            """
            SELECT count(*) AS total,
                   count(DISTINCT (cell_id, hazard_type)) AS distinct_keys
            FROM mv_latest_risk WHERE aoi_id = $1
            """,
            _AOI_ID,
        )
        # One hazard enabled: one row per cell, exactly as before the refactor.
        assert total == distinct == len(_CELLS)


async def test_second_hazard_does_not_inflate_region_counts(hazard_fixture: None) -> None:
    """The guard on the public map: counts are per cell, not per cell-hazard."""
    async with acquire() as conn:
        await _insert_assessment(
            conn, _CELLS[0], hazard=HazardType.LANDSLIDE, score=0.9, level="VeryHigh"
        )
    await _force_refresh()
    async with acquire() as conn:
        before = dict(
            await conn.fetchrow(
                "SELECT cells, high_or_above FROM v_region_tiles WHERE aoi_id = $1",
                _AOI_ID,
            )
        )

    # Enable flood and give the same cell a flood assessment too.
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = true WHERE hazard = 'flood'")
        await _insert_assessment(
            conn, _CELLS[0], hazard=HazardType.FLOOD, score=0.95, level="VeryHigh"
        )
    await _force_refresh()

    async with acquire() as conn:
        mv_rows = await conn.fetchval(
            "SELECT count(*) FROM mv_latest_risk WHERE aoi_id = $1", _AOI_ID
        )
        after = dict(
            await conn.fetchrow(
                "SELECT cells, high_or_above FROM v_region_tiles WHERE aoi_id = $1",
                _AOI_ID,
            )
        )

    # The view now carries both hazards...
    assert mv_rows == len(_CELLS) * 2
    # ...but the region rollup still counts cells once.
    assert after == before


async def test_alert_dedup_is_scoped_per_hazard(hazard_fixture: None) -> None:
    """A landslide alert must not suppress a flood alert on the same cell."""
    await insert_dispatches(
        [
            AlertDispatchRow(
                cell_id=_CELLS[0],
                aoi_id=_AOI_ID,
                level="High",
                score=0.8,
                priority=0.9,
                channels={"log": True},
                summary="frana",
                hazard_type=HazardType.LANDSLIDE,
            )
        ]
    )
    window = timedelta(hours=3)

    already = await cells_dispatched_within([_CELLS[0]], window=window, hazard=HazardType.LANDSLIDE)
    assert already == {_CELLS[0]}

    other = await cells_dispatched_within([_CELLS[0]], window=window, hazard=HazardType.FLOOD)
    assert other == set()


async def test_partitions_job_creates_and_prunes(hazard_fixture: None) -> None:
    """The job owns both halves: create ahead, drop behind."""
    from limen.agents.llm_factory.stub import StubLlmClientFactory
    from limen.api.dependencies import AppDependencies
    from limen.api.jobs.partitions import run_partitions_job
    from limen.config.settings import Settings
    from limen.data.db import get_pool

    old_day = (datetime.now(UTC) - timedelta(days=40)).date()
    part = f"risk_assessments_{old_day.strftime('%Y%m%d')}"
    async with acquire() as conn:
        await conn.fetchval(
            "SELECT ensure_partitions('risk_assessments', $1::date, $1::date)", old_day
        )

    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings.model_validate({}),
        llm_factory=StubLlmClientFactory(),
    )
    dropped = await run_partitions_job(deps)

    assert dropped["risk_assessments"] >= 1
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM pg_class WHERE relname = $1", part) == 0
        # ...and tomorrow's partition is there, so the next sweep has a home.
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y%m%d")
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM pg_class WHERE relname = $1",
                f"risk_assessments_{tomorrow}",
            )
            == 1
        )
