"""V2.x — KG client: query shape, timeout/error → empty result."""

from __future__ import annotations

import httpx
import pytest
import respx

from limen.agents.grounding.kg_client import KgClient
from limen.config.settings import KgSettings
from limen.knowledge.schema import GroundingQuery


def _query() -> GroundingQuery:
    return GroundingQuery(region="Puglia", mechanism="meteo_trigger", top_k=3)


@pytest.mark.asyncio
async def test_disabled_kg_returns_empty_without_calling_network() -> None:
    settings = KgSettings(enabled=False)
    client = KgClient(settings)
    result = await client.query(_query())
    assert result.is_empty


@pytest.mark.asyncio
@respx.mock
async def test_happy_path_returns_passages() -> None:
    settings = KgSettings(enabled=True, base_url="https://kg.test", timeout_seconds=2.0)
    body = {
        "passages": [
            {
                "source": "doi://1234",
                "title": "Caine thresholds for southern Italy",
                "snippet": "Empirical I-D thresholds calibrated for...",
                "citation": "Caine 1980; Brunetti et al. 2010",
                "score": 0.91,
            },
            {
                "source": "doi://5678",
                "title": "Post-fire destabilization in Mediterranean slopes",
                "snippet": "Burn severity correlates with ...",
                "citation": "Cannon & DeGraff 2009",
                "score": 0.74,
            },
        ]
    }
    route = respx.post("https://kg.test/query").mock(return_value=httpx.Response(200, json=body))
    client = KgClient(settings)
    result = await client.query(_query())
    assert route.called
    assert len(result.passages) == 2
    assert result.passages[0].source == "doi://1234"
    assert result.passages[0].score == pytest.approx(0.91)


@pytest.mark.asyncio
@respx.mock
async def test_query_payload_carries_thread_id_and_query() -> None:
    settings = KgSettings(enabled=True, base_url="https://kg.test")
    route = respx.post("https://kg.test/query").mock(
        return_value=httpx.Response(200, json={"passages": []})
    )
    await KgClient(settings).query(_query())
    assert route.called
    sent = route.calls[0].request
    import json as _json

    body = _json.loads(sent.content)
    assert body["thread_id"] == "landslide-kb"
    assert body["query"]["region"] == "Puglia"
    assert body["query"]["mechanism"] == "meteo_trigger"
    assert body["query"]["top_k"] == 3


@pytest.mark.asyncio
@respx.mock
async def test_5xx_returns_empty_not_raises() -> None:
    settings = KgSettings(enabled=True, base_url="https://kg.test", timeout_seconds=2.0)
    respx.post("https://kg.test/query").mock(return_value=httpx.Response(503))
    result = await KgClient(settings).query(_query())
    assert result.is_empty


@pytest.mark.asyncio
@respx.mock
async def test_timeout_returns_empty_not_raises() -> None:
    settings = KgSettings(enabled=True, base_url="https://kg.test", timeout_seconds=0.05)
    respx.post("https://kg.test/query").mock(side_effect=httpx.TimeoutException("slow"))
    result = await KgClient(settings).query(_query())
    assert result.is_empty


@pytest.mark.asyncio
@respx.mock
async def test_malformed_json_returns_empty() -> None:
    settings = KgSettings(enabled=True, base_url="https://kg.test")
    respx.post("https://kg.test/query").mock(return_value=httpx.Response(200, text="not-json"))
    result = await KgClient(settings).query(_query())
    assert result.is_empty


@pytest.mark.asyncio
@respx.mock
async def test_top_k_is_capped_client_side() -> None:
    """Sidecar returned 10 — we asked for 3 — only 3 surfaced."""
    settings = KgSettings(enabled=True, base_url="https://kg.test")
    body = {
        "passages": [
            {
                "source": f"doi://{i}",
                "title": f"Paper {i}",
                "snippet": "...",
                "citation": f"Ref {i}",
                "score": 0.9 - 0.05 * i,
            }
            for i in range(10)
        ]
    }
    respx.post("https://kg.test/query").mock(return_value=httpx.Response(200, json=body))
    result = await KgClient(settings).query(_query())
    assert len(result.passages) == 3
