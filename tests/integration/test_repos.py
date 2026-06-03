"""Repository integration tests.

Run a real PostgreSQL+PostGIS via testcontainers, apply migrations, and
exercise the AOI + grid repositories on a small AOI to keep the test fast.
Also asserts that migrations are idempotent (running them twice is a no-op).
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from limen.data.db import acquire
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import get_aoi, list_aoi_ids, upsert_aoi
from limen.data.repos.grid_repo import count_grid_cells, generate_and_store_grid

pytestmark = pytest.mark.integration


# Tiny ~5 km by 5 km test polygon near Bari (lat 41.12, lon 16.86)
_TEST_AOI_POLY = Polygon(
    [
        (16.86, 41.12),
        (16.92, 41.12),
        (16.92, 41.17),
        (16.86, 41.17),
        (16.86, 41.12),
    ]
)


async def test_migrations_are_idempotent(pg_pool: object) -> None:
    """Running migrations twice should not re-apply any files."""
    applied_again = await run_migrations()
    assert applied_again == []


async def test_postgis_extension_is_installed(pg_pool: object) -> None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT extname FROM pg_extension WHERE extname = 'postgis'")
    assert row is not None


async def test_aoi_upsert_and_get_roundtrip(reset_db: None) -> None:
    await upsert_aoi(
        id="test-bari-mini",
        name="Bari mini test AOI",
        kind="test",
        geom=_TEST_AOI_POLY,
        metadata={"source": "unit-test"},
    )
    fetched = await get_aoi("test-bari-mini")
    assert fetched is not None
    assert fetched.name == "Bari mini test AOI"
    assert fetched.geom.is_valid
    # bbox should be the envelope of the polygon
    assert fetched.bbox.is_valid

    ids = await list_aoi_ids()
    assert "test-bari-mini" in ids


async def test_grid_generation_produces_cells(reset_db: None) -> None:
    await upsert_aoi(
        id="test-bari-mini",
        name="Bari mini test AOI",
        kind="test",
        geom=_TEST_AOI_POLY,
        metadata={},
    )
    inserted_first = await generate_and_store_grid("test-bari-mini")
    total = await count_grid_cells("test-bari-mini")

    # 5 km by 5 km at 1 km cell ~ roughly 25 cells (varies with reprojection).
    assert total > 10
    assert total < 60
    assert inserted_first == total

    # Second run should be idempotent: no new inserts, same total.
    inserted_second = await generate_and_store_grid("test-bari-mini")
    assert inserted_second == 0
    assert await count_grid_cells("test-bari-mini") == total
