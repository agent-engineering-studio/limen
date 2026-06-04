"""V2.x — GroundingService cache layer."""

from __future__ import annotations

from typing import Any

import pytest

from limen.agents.grounding.kg_client import KgClient
from limen.agents.grounding.service import GroundingService, cache_key
from limen.config.settings import KgSettings
from limen.knowledge.schema import GroundingQuery, GroundingResult, Passage


class _StubCache:
    """In-memory DistributedCache stand-in."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.set_calls: int = 0

    async def get_json(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self.set_calls += 1
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _StubClient:
    """Records query calls + returns canned results."""

    def __init__(self, response: GroundingResult) -> None:
        self.response = response
        self.calls: int = 0

    async def query(self, query: GroundingQuery) -> GroundingResult:
        self.calls += 1
        return self.response


def _passage() -> Passage:
    return Passage(
        source="doi://1",
        title="Caine 1980",
        snippet="...",
        citation="Caine 1980",
        score=0.9,
    )


def _query(top_k: int = 3) -> GroundingQuery:
    return GroundingQuery(region="Puglia", mechanism="meteo_trigger", top_k=top_k)


def test_cache_key_is_stable_across_top_k_changes() -> None:
    """Same (region, mechanism) ⇒ same cache key, regardless of top_k.

    This lets a top_k=10 lookup reuse a top_k=3 cached set sliced
    client-side."""
    a = cache_key(GroundingQuery(region="Puglia", mechanism="meteo_trigger", top_k=3))
    b = cache_key(GroundingQuery(region="Puglia", mechanism="meteo_trigger", top_k=10))
    assert a == b


def test_cache_key_is_region_case_insensitive() -> None:
    a = cache_key(GroundingQuery(region="puglia", mechanism="meteo_trigger"))
    b = cache_key(GroundingQuery(region="PUGLIA", mechanism="meteo_trigger"))
    assert a == b


def test_cache_key_distinguishes_mechanism() -> None:
    a = cache_key(GroundingQuery(region="Puglia", mechanism="meteo_trigger"))
    b = cache_key(GroundingQuery(region="Puglia", mechanism="seismic_event"))
    assert a != b


@pytest.mark.asyncio
async def test_service_returns_empty_when_kg_disabled() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=False)
    service = GroundingService(settings=settings, cache=cache, client=KgClient(settings))
    result = await service.ground(_query())
    assert result.is_empty


@pytest.mark.asyncio
async def test_first_call_hits_client_second_call_hits_cache() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=True)
    response = GroundingResult(query=_query(), passages=(_passage(),))
    stub = _StubClient(response)
    service = GroundingService(settings=settings, cache=cache, client=stub)  # type: ignore[arg-type]

    a = await service.ground(_query())
    b = await service.ground(_query())

    assert stub.calls == 1, "second identical query MUST hit the cache"
    assert len(a.passages) == 1
    assert len(b.passages) == 1
    assert a.passages[0].source == b.passages[0].source


@pytest.mark.asyncio
async def test_empty_result_is_also_cached() -> None:
    """A null result is cached so we don't repeatedly query a sidecar
    whose corpus hasn't been ingested yet."""
    cache = _StubCache()
    settings = KgSettings(enabled=True)
    stub = _StubClient(GroundingResult(query=_query(), passages=()))
    service = GroundingService(settings=settings, cache=cache, client=stub)  # type: ignore[arg-type]

    await service.ground(_query())
    await service.ground(_query())
    assert stub.calls == 1


@pytest.mark.asyncio
async def test_different_mechanism_misses_cache_separately() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=True)
    stub = _StubClient(GroundingResult(query=_query(), passages=(_passage(),)))
    service = GroundingService(settings=settings, cache=cache, client=stub)  # type: ignore[arg-type]

    await service.ground(GroundingQuery(region="Puglia", mechanism="meteo_trigger"))
    await service.ground(GroundingQuery(region="Puglia", mechanism="seismic_event"))
    assert stub.calls == 2
