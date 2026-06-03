"""PostgresCache TTL + latency tests.

Marked as ``integration`` because they require Docker (testcontainers spins
up a real PostgreSQL+PostGIS instance for the session).
"""

from __future__ import annotations

import asyncio
import time

import pytest

from limen.data.caching.postgres_cache import PostgresCache

pytestmark = pytest.mark.integration


async def test_set_get_delete(clean_cache: None) -> None:
    cache = PostgresCache()
    await cache.set_json("k1", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=60)
    got = await cache.get_json("k1")
    assert got == {"a": 1, "b": [1, 2, 3]}
    await cache.delete("k1")
    assert await cache.get_json("k1") is None


async def test_ttl_expires(clean_cache: None) -> None:
    cache = PostgresCache()
    await cache.set_json("short", {"x": 1}, ttl_seconds=1)
    assert await cache.get_json("short") == {"x": 1}
    await asyncio.sleep(1.2)
    assert await cache.get_json("short") is None


async def test_cleanup_expired(clean_cache: None) -> None:
    cache = PostgresCache()
    await cache.set_json("a", {"v": 1}, ttl_seconds=1)
    await cache.set_json("b", {"v": 2}, ttl_seconds=60)
    await asyncio.sleep(1.2)
    removed = await cache.cleanup_expired()
    assert removed >= 1
    assert await cache.get_json("a") is None
    assert await cache.get_json("b") == {"v": 2}


async def test_get_latency_p95_under_10ms(clean_cache: None) -> None:
    """Sanity check that the cache is fast enough for the hot path."""
    cache = PostgresCache()
    await cache.set_json("hot", {"v": 42}, ttl_seconds=60)

    # Warm-up
    for _ in range(20):
        await cache.get_json("hot")

    samples: list[float] = []
    for _ in range(200):
        t0 = time.perf_counter()
        await cache.get_json("hot")
        samples.append((time.perf_counter() - t0) * 1000.0)

    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    assert p95 < 10.0, f"PostgresCache get p95 too slow: {p95:.2f} ms"
