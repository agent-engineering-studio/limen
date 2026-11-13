"""L'ordine dello sweep orario si legge da `job_runs`, non da `latest_risk`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from limen.api.jobs import hourly_monitoring as h
from limen.api.jobs.ids import JOB_HOURLY_MONITORING
from limen.core.models.hazard import HazardType


class _Conn:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""
        self.args: tuple[Any, ...] = ()

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        self.sql, self.args = sql, args
        return self.rows


def _con(monkeypatch: pytest.MonkeyPatch, conn: _Conn) -> None:
    @asynccontextmanager
    async def _acquire() -> AsyncIterator[_Conn]:
        yield conn

    monkeypatch.setattr(h, "acquire", _acquire)


async def test_il_pericolo_mai_valutato_va_in_testa_poi_il_piu_vecchio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = _Conn(
        [
            {"hazard_type": "landslide", "ts": datetime(2026, 11, 13, 14, 0, tzinfo=UTC)},
            {"hazard_type": "wildfire", "ts": datetime(2026, 11, 13, 12, 0, tzinfo=UTC)},
        ]
    )
    _con(monkeypatch, conn)
    ordine = await h._hazards_stale_first(
        [HazardType.LANDSLIDE, HazardType.WILDFIRE, HazardType.FLOOD]
    )
    assert ordine == [HazardType.FLOOD, HazardType.WILDFIRE, HazardType.LANDSLIDE]
    assert "FROM job_runs" in conn.sql and "latest_risk" not in conn.sql
    assert conn.args[1] == JOB_HOURLY_MONITORING


async def test_le_regioni_si_ordinano_dalle_corse_riuscite(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn([{"id": "it-toscana"}, {"id": "it-puglia"}])
    _con(monkeypatch, conn)
    assert await h._aois_stale_first(HazardType.FLOOD) == ["it-toscana", "it-puglia"]
    assert "FROM job_runs" in conn.sql and "status = 'ok'" in conn.sql
    assert conn.args[:2] == ("flood", JOB_HOURLY_MONITORING)
