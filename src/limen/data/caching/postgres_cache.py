"""Postgres-backed distributed cache.

Implements the :class:`DistributedCache` Protocol used throughout the
application. The backing table is ``app_cache`` (created by migration
``003_cache_table.sql``).

Why Postgres? Because we already have it everywhere (local & Neon) and the
hot-path requirements are modest (≤ tens of req/s, p95 < 10 ms locally).
Should we ever outgrow it, switching to Redis is a one-class change behind
the same Protocol.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import asyncpg

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@runtime_checkable
class DistributedCache(Protocol):
    """Minimal async cache contract used across Limen services."""

    async def get_json(self, key: str) -> Any | None: ...

    async def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...


class PostgresCache(DistributedCache):
    """``DistributedCache`` implementation backed by the ``app_cache`` table."""

    _GET_SQL = "SELECT value FROM app_cache WHERE key = $1 AND expires_at > now()"
    _SET_SQL = (
        "INSERT INTO app_cache (key, value, expires_at) "
        "VALUES ($1, $2::jsonb, $3) "
        "ON CONFLICT (key) DO UPDATE "
        "SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at"
    )
    _DELETE_SQL = "DELETE FROM app_cache WHERE key = $1"
    _CLEANUP_SQL = "DELETE FROM app_cache WHERE expires_at < now()"

    async def get_json(self, key: str) -> Any | None:
        async with acquire() as conn:
            row = await conn.fetchrow(self._GET_SQL, key)
        if row is None:
            return None
        value = row["value"]
        # asyncpg returns jsonb as already-parsed Python objects in some
        # configurations and as text in others. Handle both.
        return json.loads(value) if isinstance(value, str) else value

    async def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        payload = json.dumps(value, separators=(",", ":"), default=str)
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds)
        async with acquire() as conn:
            await conn.execute(self._SET_SQL, key, payload, expires_at)

    async def delete(self, key: str) -> None:
        async with acquire() as conn:
            await conn.execute(self._DELETE_SQL, key)

    async def cleanup_expired(self) -> int:
        """Delete expired rows. Returns the number of rows removed."""
        async with acquire() as conn:
            result: str = await conn.execute(self._CLEANUP_SQL)
        # asyncpg returns commands like "DELETE 17"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    @staticmethod
    async def has_pg_cron(conn: asyncpg.Connection) -> bool:
        """Return whether the ``pg_cron`` extension is installed."""
        row = await conn.fetchrow("SELECT 1 FROM pg_extension WHERE extname = 'pg_cron'")
        return row is not None
