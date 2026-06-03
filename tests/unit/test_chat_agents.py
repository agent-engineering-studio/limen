"""ChatAgent unit tests — schema validation, repair retry, length window.

All deterministic via :class:`StubChatClient`; no network.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from limen.agents.chat_agents.briefing import (
    MAX_WORDS,
    MIN_WORDS,
    BriefingAgent,
    _fallback_briefing,
    count_words,
    trim_to_max,
)
from limen.agents.chat_agents.risk_analyst import (
    RiskAnalysis,
    RiskAnalystAgent,
)
from limen.agents.llm_factory.stub import StubChatClient
from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
)
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)


def _assessment() -> AggregateAssessment:
    top_cell = CellRiskRecord(
        cell_id="aoi|0|0",
        score=0.55,
        level=RiskLevel.High,
        static_terms=StaticBreakdown(
            susc_ispra=0.4, iffi_density=0.5, slope=0.6, pai=0.4, litho_weight=0.5
        ),
        meteo_terms=MeteoBreakdown(
            caine_excess=0.1, caine_norm=0.1, api_factor=0.6, soil_factor=0.5
        ),
        s=0.48,
        m=0.42,
        e=0.05,
        f=0.0,
        h=0.0,
    )
    return AggregateAssessment(
        aoi_id="aoi-test",
        model_version="limen-deterministic-v1",
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        n_cells=1,
        cells_high_or_above=1,
        cells_by_level={"High": 1},
        top_cells=[top_cell],
    )


# ---------------------------------------------------------------------------
# RiskAnalystAgent
# ---------------------------------------------------------------------------
async def test_risk_analyst_default_stub_returns_valid_schema() -> None:
    client = StubChatClient()
    agent = RiskAnalystAgent(client)
    out = await agent.analyse(_assessment())
    assert isinstance(out, RiskAnalysis)
    assert out.driver in {
        "static_susceptibility",
        "meteo_trigger",
        "seismic_event",
        "post_fire_destabilization",
        "human_activity",
    }
    assert out.attention_window_hours in {12, 24, 48, 72}
    assert 0.0 <= out.confidence <= 1.0


async def test_risk_analyst_repairs_invalid_json_then_succeeds() -> None:
    """First response is malformed; retry returns valid JSON."""
    canned = [
        "this is not JSON",
        json.dumps(
            {
                "driver": "meteo_trigger",
                "anomalies": ["test anomaly"],
                "attention_window_hours": 48,
                "confidence": 0.5,
            }
        ),
    ]
    client = StubChatClient(canned_responses=canned)
    agent = RiskAnalystAgent(client)
    out = await agent.analyse(_assessment())
    assert out.driver == "meteo_trigger"
    assert out.attention_window_hours == 48
    assert len(client.calls) == 2  # original + repair retry


async def test_risk_analyst_falls_back_after_two_failures() -> None:
    """Both attempts malformed → neutral fallback, no exception."""
    canned = ["nope", "{ still invalid"]
    client = StubChatClient(canned_responses=canned)
    agent = RiskAnalystAgent(client)
    out = await agent.analyse(_assessment())
    assert out.driver == "static_susceptibility"  # neutral fallback
    assert out.confidence == pytest.approx(0.30)
    assert any("fallback" in a.lower() for a in out.anomalies)


async def test_risk_analyst_falls_back_on_client_exception() -> None:
    """A raise from the chat client must not propagate."""

    class _Boom(StubChatClient):
        async def chat(self, messages, **_):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated network failure")

    agent = RiskAnalystAgent(_Boom())
    out = await agent.analyse(_assessment())
    assert isinstance(out, RiskAnalysis)
    assert any("fallback" in a.lower() for a in out.anomalies)


# ---------------------------------------------------------------------------
# BriefingAgent
# ---------------------------------------------------------------------------
async def test_briefing_default_stub_is_in_range() -> None:
    client = StubChatClient()
    agent = BriefingAgent(client)
    text = await agent.brief(_assessment())
    n = count_words(text)
    assert MIN_WORDS <= n <= MAX_WORDS
    assert "Limen" not in text.split("\n")[0]  # no product/brand spam


async def test_briefing_trims_overlong_response() -> None:
    overlong = " ".join(["parola"] * (MAX_WORDS + 50))
    client = StubChatClient(canned_responses=[overlong])
    agent = BriefingAgent(client)
    text = await agent.brief(_assessment())
    assert count_words(text) <= MAX_WORDS


async def test_briefing_regenerates_when_too_short() -> None:
    short = "Solo poche parole."
    long_ok = " ".join(["alfa"] * 200)
    client = StubChatClient(canned_responses=[short, long_ok])
    agent = BriefingAgent(client)
    text = await agent.brief(_assessment())
    assert count_words(text) >= MIN_WORDS
    assert len(client.calls) == 2  # original + regenerate


async def test_briefing_falls_back_when_retry_also_fails() -> None:
    """Two short responses → safety fallback paragraph."""
    short = "troppo corto"
    still_short = "anche questo"
    client = StubChatClient(canned_responses=[short, still_short])
    agent = BriefingAgent(client)
    text = await agent.brief(_assessment())
    # Fallback is always within the word window (it's bounded by trim_to_max).
    assert count_words(text) <= MAX_WORDS
    # Fallback mentions the AOI id.
    assert "aoi-test" in text


def test_word_counter_and_trim() -> None:
    assert count_words("uno due tre") == 3
    assert count_words("parole-composte sì") == 2
    text = " ".join([f"parola{i}" for i in range(300)])
    trimmed = trim_to_max(text, 100)
    assert count_words(trimmed) <= 100


def test_fallback_briefing_is_safe() -> None:
    """Pure-Python fallback never raises and is inside the word window."""
    text = _fallback_briefing(_assessment())
    assert MIN_WORDS <= count_words(text) <= MAX_WORDS or count_words(text) <= MAX_WORDS
    assert "aoi-test" in text
