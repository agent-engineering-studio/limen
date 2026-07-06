"""Unit checks for the forecast pipeline (CLI + scheduled job helpers)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from limen.agents.workflows.forecast import ClampedApiClient, ForecastRun
from limen.api.jobs.forecast_monitoring import build_forecast_payload
from limen.core.models.context import CellRiskRecord
from limen.core.models.risk import MeteoBreakdown, RiskLevel, StaticBreakdown
from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient

_BBOX = (6.8, 45.5, 7.9, 46.0)


@pytest.mark.asyncio
async def test_future_as_of_is_clamped_to_today(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    async def fake_get_api(
        self: CachedOpenMeteoClient, *, aoi_id: str, bbox: Any, as_of: date, days: int
    ) -> dict[str, float]:
        seen["as_of"] = as_of
        return {f"api_{days}d": 0.0}

    monkeypatch.setattr(CachedOpenMeteoClient, "get_api", fake_get_api)
    client = ClampedApiClient()
    today = datetime.now(UTC).date()

    await client.get_api(aoi_id="x", bbox=_BBOX, as_of=today + timedelta(days=2), days=30)
    assert seen["as_of"] == today

    past = today - timedelta(days=10)
    await client.get_api(aoi_id="x", bbox=_BBOX, as_of=past, days=30)
    assert seen["as_of"] == past


def _cell(cell_id: str, score: float, level: RiskLevel) -> CellRiskRecord:
    return CellRiskRecord(
        cell_id=cell_id,
        score=score,
        level=level,
        static_terms=StaticBreakdown(
            susc_ispra=0.5, iffi_density=0.5, slope=0.5, pai=0.5, litho_weight=0.5
        ),
        meteo_terms=MeteoBreakdown(
            caine_excess=0.0, caine_norm=0.5, api_factor=0.5, soil_factor=0.5
        ),
        s=0.8,
        m=0.5,
        e=0.1,
        f=0.0,
        h=0.0,
    )


def test_forecast_payload_is_labelled_and_deterministic() -> None:
    cells = [
        _cell("aoi|1|1", 0.71, RiskLevel.High),
        _cell("aoi|2|2", 0.65, RiskLevel.High),
        _cell("aoi|3|3", 0.30, RiskLevel.Low),
    ]
    run = ForecastRun(
        aoi_id="it-test",
        horizon_h=48,
        valuation_time=datetime(2026, 7, 8, 12, 0, tzinfo=UTC),
        cell_results=cells,
    )
    triggered = [c for c in cells if c.level is RiskLevel.High]

    payload = build_forecast_payload(run, triggered)

    assert payload.pipeline_version == "v1-forecast+48h"
    assert payload.summary_it.startswith("PREVISIONE Limen a +48 ore")
    assert "0.71" in payload.summary_it
    assert payload.max_level is RiskLevel.High
    assert [c.cell_id for c in payload.cells][:2] == ["aoi|1|1", "aoi|2|2"]
    # Deterministic: same input, same summary (no LLM in the alert path).
    assert build_forecast_payload(run, triggered).summary_it == payload.summary_it
