"""Shared pytest fixtures.

A real PostgreSQL + PostGIS instance is spun up once per test session via
``testcontainers``. Tests that need it should depend on the ``pg_pool``
fixture; the fixture takes care of init/migrate/teardown.
"""

from __future__ import annotations

import contextlib
import os
import platform
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import asyncpg


def _default_postgis_image() -> str:
    """Pick a PostGIS image with a manifest for the current arch.

    The official ``postgis/postgis:16-3.5`` image does not currently ship an
    arm64 manifest. ``imresamu/postgis-arm64:16-3.5`` is a well-maintained
    community fork with arm64 binaries. Override with ``LIMEN_TEST_POSTGIS_IMAGE``
    to point at any other PostGIS-equipped Postgres image.
    """
    override = os.getenv("LIMEN_TEST_POSTGIS_IMAGE")
    if override:
        return override
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        return "imresamu/postgis-arm64:16-3.5"
    return "postgis/postgis:16-3.5"


POSTGIS_IMAGE = _default_postgis_image()


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[str]:
    """Spin up Postgres+PostGIS via testcontainers and yield the DSN."""
    pytest.importorskip("testcontainers.postgres")
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer(
        image=POSTGIS_IMAGE, username="limen", password="limen", dbname="limen"
    )
    container.start()
    try:
        dsn = container.get_connection_url()
        # testcontainers returns SQLAlchemy URLs (postgresql+psycopg2://…);
        # asyncpg wants a plain postgresql:// DSN.
        dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
        dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
        yield dsn
    finally:
        container.stop()


@pytest.fixture(scope="session")
async def pg_pool(postgres_container: str) -> AsyncIterator[asyncpg.Pool]:
    """Initialise the Limen pool against the testcontainer and apply migrations.

    Session-scoped: pytest-asyncio gives us a session-wide loop (configured in
    pyproject.toml via ``asyncio_default_fixture_loop_scope = "session"``).
    Re-creating the pool per test would race against that loop's lifecycle.
    Test isolation is provided by the ``reset_db`` / ``clean_cache`` fixtures.
    """
    from limen.config.settings import DBSettings
    from limen.data import db as db_mod
    from limen.data.migrate import run_migrations

    await db_mod.close_pool()
    settings = DBSettings(
        connection_string=postgres_container, pool_min_size=1, pool_max_size=4
    )
    pool = await db_mod.init_pool(settings)
    await run_migrations()
    try:
        yield pool
    finally:
        await db_mod.close_pool()


@pytest.fixture()
async def reset_db(pg_pool: asyncpg.Pool) -> AsyncIterator[None]:
    """Truncate test-mutated tables before each test that needs isolation."""
    from limen.data.db import acquire

    async with acquire() as conn:
        with contextlib.suppress(Exception):
            await conn.execute(
                "TRUNCATE app_cache, risk_assessments, susceptibility, "
                "cell_static_factors, grid_cells, aoi RESTART IDENTITY CASCADE"
            )
    yield


@pytest.fixture()
async def clean_cache(pg_pool: asyncpg.Pool) -> AsyncIterator[None]:
    """Truncate the cache table before a test that exercises it."""
    from limen.data.db import acquire

    async with acquire() as conn:
        with contextlib.suppress(Exception):
            await conn.execute("TRUNCATE app_cache")
    yield
