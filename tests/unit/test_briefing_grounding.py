"""V2.x — BriefingAgent with vs without the KG grounding service."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import pytest

from limen.agents.chat_agents.briefing import BriefingAgent
from limen.agents.chat_agents.risk_analyst import RiskAnalysis
from limen.agents.grounding.service import GroundingService
from limen.agents.llm_factory.base import ChatMessage
from limen.config.settings import KgSettings
from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
)
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)
from limen.knowledge.schema import GroundingQuery, GroundingResult, Passage


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class _FakeChatClient:
    """Returns a single canned 200-word briefing every time."""

    def __init__(self, text: str | None = None, raise_on_call: bool = False) -> None:
        self._text = text or _two_hundred_words()
        self._raise = raise_on_call
        self.calls: int = 0

    async def chat(self, messages: list[ChatMessage], **_: Any) -> str:
        self.calls += 1
        if self._raise:
            raise RuntimeError("LLM unreachable")
        return self._text


def _two_hundred_words() -> str:
    # 200 distinct tokens — easily inside the 150-250 band.
    return " ".join(f"parola{i}" for i in range(200))


class _StubCache:
    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def get_json(self, key: str) -> Any | None:
        return self.store.get(key)

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _SlowKgClient:
    """KG client whose query takes longer than the configured timeout."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay = delay_seconds
        self.calls: int = 0

    async def query(self, query: GroundingQuery) -> GroundingResult:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return GroundingResult(query=query, passages=())


class _OkKgClient:
    """KG client returning one canned passage tied to the query mechanism."""

    def __init__(self, mechanism: str) -> None:
        self._mechanism = mechanism

    async def query(self, query: GroundingQuery) -> GroundingResult:
        return GroundingResult(
            query=query,
            passages=(
                Passage(
                    source="doi://caine-1980",
                    title=f"Threshold paper for {query.region}",
                    snippet="Empirical I-D threshold...",
                    citation="Caine 1980; Brunetti et al. 2010",
                    score=0.92,
                ),
            ),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _assessment() -> AggregateAssessment:
    return AggregateAssessment(
        aoi_id="it-puglia",
        model_version="v1.0-test",
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        n_cells=3,
        cells_high_or_above=0,
        cells_by_level={"None": 2, "Low": 1},
        top_cells=[
            CellRiskRecord(
                cell_id="it-puglia|0|0",
                score=0.12,
                level=RiskLevel.Low,
                static_terms=StaticBreakdown(
                    susc_ispra=0.3,
                    iffi_density=0.1,
                    slope=0.4,
                    pai=0.2,
                    litho_weight=0.3,
                ),
                meteo_terms=MeteoBreakdown(
                    caine_excess=0.0,
                    caine_norm=0.1,
                    api_factor=0.3,
                    soil_factor=0.4,
                ),
                s=0.27,
                m=0.21,
                e=0.0,
                f=0.0,
                h=0.0,
            )
        ],
    )


def _analysis() -> RiskAnalysis:
    return RiskAnalysis(
        driver="meteo_trigger",
        anomalies=[],
        attention_window_hours=24,
        confidence=0.78,
    )


# ---------------------------------------------------------------------------
# Behaviour — without grounding, briefing is unchanged
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_briefing_without_grounding_carries_no_citations() -> None:
    agent = BriefingAgent(_FakeChatClient(), grounding=None)
    text = await agent.brief(_assessment(), analysis=_analysis())
    assert "Fonti" not in text


# ---------------------------------------------------------------------------
# Behaviour — with grounding up, briefing carries a citation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_briefing_with_grounding_appends_citation() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=True, timeout_seconds=2.0)
    service = GroundingService(
        settings=settings,
        cache=cache,
        client=_OkKgClient("meteo_trigger"),  # type: ignore[arg-type]
    )
    agent = BriefingAgent(_FakeChatClient(), grounding=service)
    text = await agent.brief(_assessment(), analysis=_analysis())
    assert "Fonti" in text
    assert "Caine 1980" in text


# ---------------------------------------------------------------------------
# Behaviour — KG slow / down, briefing still emits, no citations, no stall
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_briefing_with_kg_timeout_emits_without_citations() -> None:
    cache = _StubCache()
    # KG client sleeps 5s but the service timeout is 0.05s.
    settings = KgSettings(enabled=True, timeout_seconds=0.05)
    service = GroundingService(
        settings=settings,
        cache=cache,
        client=_SlowKgClient(delay_seconds=5.0),  # type: ignore[arg-type]
    )
    agent = BriefingAgent(_FakeChatClient(), grounding=service)
    start = time.monotonic()
    text = await agent.brief(_assessment(), analysis=_analysis())
    elapsed = time.monotonic() - start
    # No citations because the KG timed out.
    assert "Fonti" not in text
    # Critical-path invariance: the entire briefing must complete in
    # well under the KG client's 5s sleep — the service-level timeout
    # ceiling kicks in long before that.
    assert elapsed < 1.0, f"KG timeout leaked into critical path: {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_briefing_with_kg_disabled_skips_grounding_entirely() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=False)
    service = GroundingService(
        settings=settings,
        cache=cache,
        client=_OkKgClient("meteo_trigger"),  # type: ignore[arg-type]
    )
    agent = BriefingAgent(_FakeChatClient(), grounding=service)
    text = await agent.brief(_assessment(), analysis=_analysis())
    assert "Fonti" not in text


# ---------------------------------------------------------------------------
# Behaviour — analysis missing ⇒ no KG call (driver is required)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_briefing_skips_grounding_without_analysis() -> None:
    cache = _StubCache()
    settings = KgSettings(enabled=True)
    client = _OkKgClient("meteo_trigger")
    service = GroundingService(
        settings=settings,
        cache=cache,
        client=client,  # type: ignore[arg-type]
    )
    agent = BriefingAgent(_FakeChatClient(), grounding=service)
    text = await agent.brief(_assessment(), analysis=None)
    assert "Fonti" not in text


# ---------------------------------------------------------------------------
# Critical-path latency — KG down doesn't slow scoring
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_kg_failure_does_not_block_llm_path() -> None:
    """If the LLM call raises, the KG task is cancelled and we fall back fast."""
    cache = _StubCache()
    # KG sleeps long enough that, if it weren't cancelled, the test
    # would take 5 seconds. We expect it to abort under a second.
    settings = KgSettings(enabled=True, timeout_seconds=5.0)
    service = GroundingService(
        settings=settings,
        cache=cache,
        client=_SlowKgClient(delay_seconds=5.0),  # type: ignore[arg-type]
    )
    agent = BriefingAgent(_FakeChatClient(raise_on_call=True), grounding=service)
    start = time.monotonic()
    text = await agent.brief(_assessment(), analysis=_analysis())
    elapsed = time.monotonic() - start
    # Deterministic fallback briefing — no citations, no stall.
    assert "modalità di sicurezza" in text
    assert elapsed < 1.0, f"LLM failure path leaked: {elapsed:.2f}s"
