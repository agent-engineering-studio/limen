"""Grounding service — :class:`KgClient` + ``app_cache`` by (region, mechanism).

The cache key is intentionally narrow:

* ``region`` — the AOI's administrative region;
* ``mechanism`` — the RiskAnalyst's driver enum.

Same (region, mechanism) → same citations within the TTL. Different
top-K requests reuse the cached set; we slice client-side so the cache
hit stays warm regardless of the requested page size.

A cache MISS that yields an empty result is also persisted so we don't
hammer the sidecar with the same null query within the window — a
common "the KG isn't ingested yet" pattern.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from limen.agents.grounding.kg_client import KgClient
from limen.config.settings import KgSettings
from limen.core.logging import get_logger
from limen.data.caching.postgres_cache import DistributedCache
from limen.knowledge.schema import GroundingQuery, GroundingResult, Passage

_log: structlog.stdlib.BoundLogger = get_logger(__name__)

# Cache key prefix — keep stable so a YAML / library refactor doesn't
# accidentally invalidate the live deployment's cache.
_CACHE_PREFIX = "kg.grounding.v1"


def _normalise_region(region: str) -> str:
    return region.strip().lower().replace(" ", "-")


def cache_key(query: GroundingQuery) -> str:
    return f"{_CACHE_PREFIX}|{_normalise_region(query.region)}|{query.mechanism.lower()}"


class GroundingService:
    """Cached KG client with a hard timeout ceiling.

    The advisory contract: ``ground(query)`` always returns a typed
    :class:`GroundingResult`. Empty passages = "no citations" — the
    BriefingAgent's job is to render only what's present.
    """

    def __init__(
        self,
        *,
        settings: KgSettings,
        cache: DistributedCache,
        client: KgClient | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._client = client or KgClient(settings)

    @property
    def settings(self) -> KgSettings:
        return self._settings

    async def ground(self, query: GroundingQuery) -> GroundingResult:
        if not self._settings.enabled:
            return GroundingResult(query=query, passages=())

        key = cache_key(query)
        cached = await self._safe_cache_get(key)
        if cached is not None:
            return _materialise_from_cache(query, cached)

        try:
            result = await asyncio.wait_for(
                self._client.query(query),
                timeout=self._settings.timeout_seconds,
            )
        except TimeoutError:
            _log.warning(
                "kg.ground.timeout_outer",
                timeout_s=self._settings.timeout_seconds,
            )
            result = GroundingResult(query=query, passages=())

        await self._safe_cache_set(key, _to_cacheable(result))
        return result

    async def _safe_cache_get(self, key: str) -> Any | None:
        try:
            return await self._cache.get_json(key)
        except Exception as exc:
            _log.warning("kg.ground.cache_get_error", error=str(exc), key=key)
            return None

    async def _safe_cache_set(self, key: str, value: Any) -> None:
        try:
            await self._cache.set_json(key, value, ttl_seconds=self._settings.cache_ttl_seconds)
        except Exception as exc:
            _log.warning("kg.ground.cache_set_error", error=str(exc), key=key)


def _to_cacheable(result: GroundingResult) -> dict[str, Any]:
    return {
        "passages": [p.model_dump(mode="json") for p in result.passages],
    }


def _materialise_from_cache(query: GroundingQuery, raw: Any) -> GroundingResult:
    if not isinstance(raw, dict):
        return GroundingResult(query=query, passages=())
    items = raw.get("passages") or []
    out: list[Passage] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                try:
                    out.append(Passage.model_validate(item))
                except Exception:
                    continue
    return GroundingResult(query=query, passages=tuple(out[: query.top_k]))


__all__ = ["GroundingService", "cache_key"]
