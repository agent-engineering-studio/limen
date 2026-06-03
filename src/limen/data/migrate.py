"""Idempotent SQL migration runner.

Design goals:

* Pure-SQL migrations under :mod:`limen.data.migrations` — no Alembic, no
  Django, no ORM lock-in. The runner does not parse the SQL, it just
  executes each file and records the filename in ``schema_migrations``.
* Identical behaviour on local Docker PostgreSQL+PostGIS and on Neon
  (serverless). The optional ``pg_cron`` extension is created inside the SQL
  files inside a ``DO`` block that swallows errors, so missing-on-Neon is
  fine.
* Safe to run multiple times. Each file's checksum is recorded; running the
  same file again is a no-op, running it with different content is an error.
"""

from __future__ import annotations

import hashlib
from importlib import resources
from typing import TYPE_CHECKING

import asyncpg

from limen.core.logging import get_logger
from limen.data.db import acquire

if TYPE_CHECKING:
    from collections.abc import Iterable

log = get_logger(__name__)

MIGRATIONS_PACKAGE = "limen.data.migrations"


_BOOTSTRAP_SQL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    name        text PRIMARY KEY,
    checksum    text NOT NULL,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def _discover_migrations() -> list[tuple[str, str]]:
    """Return a sorted list of ``(filename, sql_text)`` pairs."""
    files = sorted(
        f.name
        for f in resources.files(MIGRATIONS_PACKAGE).iterdir()
        if f.is_file() and f.name.endswith(".sql")
    )
    out: list[tuple[str, str]] = []
    for name in files:
        ref = resources.files(MIGRATIONS_PACKAGE).joinpath(name)
        out.append((name, ref.read_text(encoding="utf-8")))
    return out


def _checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _already_applied(
    conn: asyncpg.Connection,
    name: str,
) -> str | None:
    row = await conn.fetchrow("SELECT checksum FROM schema_migrations WHERE name = $1", name)
    return None if row is None else str(row["checksum"])


async def run_migrations(only: Iterable[str] | None = None) -> list[str]:
    """Apply pending migrations.

    Args:
        only: Optional iterable of migration filenames to restrict the run to.

    Returns:
        The list of migration filenames that were applied during this call.
    """
    applied_now: list[str] = []
    whitelist = set(only) if only is not None else None

    async with acquire() as conn:
        await conn.execute(_BOOTSTRAP_SQL)

        for name, sql in _discover_migrations():
            if whitelist is not None and name not in whitelist:
                continue

            cs = _checksum(sql)
            previous = await _already_applied(conn, name)

            if previous is not None:
                if previous != cs:
                    raise RuntimeError(
                        f"Migration {name!r} has changed since it was applied "
                        f"(stored checksum={previous}, current={cs}). "
                        "Create a new migration file instead of editing applied ones."
                    )
                log.debug("migrate.skip", file=name)
                continue

            log.info("migrate.apply", file=name)
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)",
                    name,
                    cs,
                )
            applied_now.append(name)

    log.info("migrate.done", applied=len(applied_now), files=applied_now)
    return applied_now
