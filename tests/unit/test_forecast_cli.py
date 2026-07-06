"""Unit checks for the ``limen forecast`` CLI helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from limen.cli.forecast import _ClampedApiClient
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
    client = _ClampedApiClient()
    today = datetime.now(UTC).date()

    await client.get_api(aoi_id="x", bbox=_BBOX, as_of=today + timedelta(days=2), days=30)
    assert seen["as_of"] == today

    past = today - timedelta(days=10)
    await client.get_api(aoi_id="x", bbox=_BBOX, as_of=past, days=30)
    assert seen["as_of"] == past
