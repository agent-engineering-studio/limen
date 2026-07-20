"""Flood-signal fetch: executor wiring + client parsing/degradation (issue #8)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from limen.agents.executors.flood_forecast_fetch import FloodForecastFetchExecutor
from limen.core.models.context import MonitoringContext
from limen.integrations.openmeteo.flood import FloodSignals, OpenMeteoFloodClient

_T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class _FakeClient:
    def __init__(self, sig: FloodSignals) -> None:
        self._sig = sig

    async def fetch_signals(self, **_kw: Any) -> FloodSignals:
        return self._sig


@pytest.mark.asyncio
async def test_executor_sets_signals_on_context() -> None:
    ctx = MonitoringContext(aoi_id="it-puglia", valuation_time=_T0, bbox=(16.0, 40.0, 17.0, 41.0))
    client = _FakeClient(
        FloodSignals(rain_72h_mm=120.0, river_discharge_ratio=3.0, coastal_surge_norm=0.2)
    )
    out = await FloodForecastFetchExecutor(client=client).run(ctx)
    assert out.flood_forecast_rain_72h_mm == 120.0
    assert out.river_discharge_ratio == 3.0
    assert out.coastal_surge_norm == 0.2


@pytest.mark.asyncio
async def test_executor_without_bbox_is_a_noop() -> None:
    ctx = MonitoringContext(aoi_id="it-puglia", valuation_time=_T0)
    out = await FloodForecastFetchExecutor(client=_FakeClient(FloodSignals())).run(ctx)
    assert out.flood_forecast_rain_72h_mm is None


@pytest.mark.asyncio
async def test_client_pluvial_sums_precip(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        return {"hourly": {"precipitation": [1.0, 2.0, None, 3.0]}}

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._pluvial(16.0, 41.0, _T0, 72) == 6.0


@pytest.mark.asyncio
async def test_client_fluvial_ratio_peak_over_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        # 31 past days at 10 + 7 forecast with a peak of 30 → 30 / 10 = 3.0
        return {
            "daily": {"river_discharge": [10.0] * 31 + [30.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]}
        }

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._fluvial(16.0, 41.0) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_client_coastal_none_inland(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        return {"hourly": {"wave_height": []}}  # inland → no marine data

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._coastal(16.0, 41.0) is None


@pytest.mark.asyncio
async def test_client_degrades_to_none_when_get_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> None:
        return None  # simulate a degraded HTTP fetch

    monkeypatch.setattr(c, "_get", fake_get)
    sig = await c.fetch_signals(bbox=(16.0, 40.0, 17.0, 41.0), valuation_time=_T0)
    assert sig == FloodSignals(None, None, None)
