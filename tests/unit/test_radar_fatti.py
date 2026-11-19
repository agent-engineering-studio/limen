"""I fatti del radar nel server MCP (#643): la risposta di dpc-radar, o {} se la sorgente manca."""

from __future__ import annotations

from typing import Any

import pytest
from dpc_radar import DpcRadarError

from limen.integrations.dpc import fatti
from limen.mcp import tools


class _Guasto:
    async def rain_at(self, *_a: Any) -> dict[str, Any]:
        raise DpcRadarError("the newest CUM24 frame is not available")


class _Buono:
    async def rain_at(self, lon: float, lat: float, hours: int) -> dict[str, Any]:
        return {"lon": lon, "lat": lat, "hours": hours, "mm": 12.5}


async def test_la_risposta_arriva_com_e(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fatti, "fatti", lambda: _Buono())
    assert await tools.radar_rain_at(15.0, 41.0, 3) == {
        "lon": 15.0,
        "lat": 41.0,
        "hours": 3,
        "mm": 12.5,
    }


async def test_una_sorgente_che_manca_da_un_dizionario_vuoto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fatti, "fatti", lambda: _Guasto())
    assert await tools.radar_rain_at(15.0, 41.0) == {}


def test_la_rarita_non_chiede_niente_alla_rete() -> None:
    r = tools.radar_rarity(15.78, 37.92, 24, 180.0)
    assert r["return_period_years"] == 50.0
    assert r["at_least"] is True
