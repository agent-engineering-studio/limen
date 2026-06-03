"""Cache-first wrapper around :class:`OpenMeteoHttpClient`.

Key shape: ``meteo:{aoi_id}:{window_start_iso}:{window_end_iso}``.
TTL: 30 minutes (forecast volatility / freshness trade-off).

The wrapper conforms to the same Protocol as the underlying client so
callers can swap implementations freely.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from limen.core.logging import get_logger
from limen.data.caching.postgres_cache import DistributedCache, PostgresCache
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import MeteoSnapshot

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

DEFAULT_TTL_SECONDS = 30 * 60
_SNAPSHOT_ADAPTER = TypeAdapter(MeteoSnapshot)


def _snapshot_key(
    *,
    aoi_id: str,
    window_start: datetime,
    window_end: datetime,
) -> str:
    return f"meteo:{aoi_id}:{window_start.isoformat()}:{window_end.isoformat()}"


def _api_key(*, aoi_id: str, as_of: date, days: int) -> str:
    return f"meteo:api:{aoi_id}:{as_of.isoformat()}:{days}"


class CachedOpenMeteoClient:
    """Cache-first decorator around :class:`OpenMeteoHttpClient`.

    Conforms to the :class:`OpenMeteoClient` Protocol. A second identical
    request within ``ttl_seconds`` is served from PostgresCache with zero
    HTTP calls.
    """

    def __init__(
        self,
        *,
        upstream: OpenMeteoHttpClient | None = None,
        cache: DistributedCache | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._upstream = upstream or OpenMeteoHttpClient()
        self._cache: DistributedCache = cache or PostgresCache()
        self._ttl = ttl_seconds

    async def get_meteo_snapshot(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        window_start: datetime,
        window_end: datetime,
    ) -> MeteoSnapshot | None:
        key = _snapshot_key(aoi_id=aoi_id, window_start=window_start, window_end=window_end)

        cached = await self._cache.get_json(key)
        if cached is not None:
            log.debug("openmeteo.cache.hit", key=key)
            return _SNAPSHOT_ADAPTER.validate_python(cached)

        log.debug("openmeteo.cache.miss", key=key)
        snapshot = await self._upstream.get_meteo_snapshot(
            aoi_id=aoi_id,
            bbox=bbox,
            window_start=window_start,
            window_end=window_end,
        )
        if snapshot is not None:
            await self._cache.set_json(
                key,
                snapshot.model_dump(mode="json"),
                ttl_seconds=self._ttl,
            )
        return snapshot

    async def get_api(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        as_of: date,
        days: int,
    ) -> dict[str, float]:
        key = _api_key(aoi_id=aoi_id, as_of=as_of, days=days)

        cached = await self._cache.get_json(key)
        if cached is not None:
            log.debug("openmeteo.cache.hit", key=key)
            return dict(cached)

        log.debug("openmeteo.cache.miss", key=key)
        result: dict[str, float] = await self._upstream.get_api(
            aoi_id=aoi_id,
            bbox=bbox,
            as_of=as_of,
            days=days,
        )
        if result:
            await self._cache.set_json(key, result, ttl_seconds=self._ttl)
        return result
