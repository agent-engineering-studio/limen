"""AlertDispatchExecutor integration tests.

Exercises the threshold gate + dedup window + persistence side-effects
of the real (non-stub) executor against a fresh testcontainers Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shapely.geometry import Polygon

from limen.agents.executors.alert_dispatch import AlertDispatchExecutor
from limen.config.settings import AlertSettings
from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
    MonitoringContext,
)
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)
from limen.data.db import acquire
from limen.data.repos.alert_dispatches_repo import count_dispatches, fetch_recent
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.notifications.base import AlertPayload, NotificationChannel
from limen.notifications.dispatcher import NotificationDispatcher

pytestmark = pytest.mark.integration

_AOI = Polygon(
    [
        (16.86, 41.12),
        (16.88, 41.12),
        (16.88, 41.14),
        (16.86, 41.14),
        (16.86, 41.12),
    ]
)
_AOI_ID = "alert-test"


class _CaptureChannel(NotificationChannel):
    """Records every payload it sees so assertions can be precise."""

    name = "capture"
    is_enabled = True

    def __init__(self) -> None:
        self.received: list[AlertPayload] = []

    async def send(self, payload: AlertPayload) -> bool:
        self.received.append(payload)
        return True


def _cell(cell_id: str, *, score: float, level: RiskLevel) -> CellRiskRecord:
    return CellRiskRecord(
        cell_id=cell_id,
        score=score,
        level=level,
        s=score,
        m=score,
        e=0.0,
        f=0.0,
        h=0.0,
        static_terms=StaticBreakdown(
            susc_ispra=0.0, iffi_density=0.0, slope=0.0, pai=0.0, litho_weight=0.0
        ),
        meteo_terms=MeteoBreakdown(
            caine_excess=0.0, caine_norm=0.0, api_factor=0.5, soil_factor=0.5
        ),
    )


async def _seed_aoi_with_cells() -> list[str]:
    await upsert_aoi(id=_AOI_ID, name="alert test", kind="test", geom=_AOI)
    await generate_and_store_grid(_AOI_ID)
    # cell_static_factors rows (NULL exposure → priority == score).
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 3",
            _AOI_ID,
        )
        ids = [str(r["id"]) for r in rows]
        for cid in ids:
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id) VALUES ($1) "
                "ON CONFLICT (cell_id) DO NOTHING",
                cid,
            )
    return ids


def _ctx(cells: list[CellRiskRecord]) -> MonitoringContext:
    return MonitoringContext(
        aoi_id=_AOI_ID,
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        cell_ids=tuple(c.cell_id for c in cells),
        cell_results=cells,
        assessment=AggregateAssessment(
            aoi_id=_AOI_ID,
            model_version="limen-deterministic-v1",
            valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            n_cells=len(cells),
            cells_high_or_above=sum(
                1 for c in cells if c.level in {RiskLevel.High, RiskLevel.VeryHigh}
            ),
            cells_by_level={"High": sum(1 for c in cells if c.level == RiskLevel.High)},
            top_cells=cells,
        ),
    )


async def test_below_threshold_does_not_dispatch(reset_db: None) -> None:
    cell_ids = await _seed_aoi_with_cells()
    assert cell_ids
    cells = [_cell(cell_ids[0], score=0.40, level=RiskLevel.Moderate)]
    capture = _CaptureChannel()
    executor = AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    )
    result = await executor.run(_ctx(cells))
    assert result.dispatched_alerts == []
    assert capture.received == []
    assert await count_dispatches() == 0


async def test_high_level_dispatches_and_persists(reset_db: None) -> None:
    cell_ids = await _seed_aoi_with_cells()
    cells = [
        _cell(cell_ids[0], score=0.80, level=RiskLevel.VeryHigh),
        _cell(cell_ids[1], score=0.62, level=RiskLevel.High),
    ]
    capture = _CaptureChannel()
    executor = AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    )
    result = await executor.run(_ctx(cells))

    assert len(capture.received) == 1
    payload = capture.received[0]
    assert payload.max_level == RiskLevel.VeryHigh
    # both cells flagged; priority order keeps the higher-score cell first
    assert payload.cells[0].cell_id == cell_ids[0]
    assert len(result.dispatched_alerts) == 2
    assert await count_dispatches() == 2
    persisted = await fetch_recent(aoi_id=_AOI_ID)
    assert persisted[0]["channels"] == {"capture": True}


async def test_dedup_window_suppresses_repeat(reset_db: None) -> None:
    """Two back-to-back dispatches for the same cell → second is suppressed."""
    cell_ids = await _seed_aoi_with_cells()
    cells = [_cell(cell_ids[0], score=0.80, level=RiskLevel.VeryHigh)]
    capture = _CaptureChannel()
    executor = AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    )

    await executor.run(_ctx(cells))
    assert len(capture.received) == 1
    assert await count_dispatches() == 1

    # Second run inside the dedup window — same cell, no new dispatch.
    await executor.run(_ctx(cells))
    assert len(capture.received) == 1
    assert await count_dispatches() == 1


async def test_dedup_window_expires(reset_db: None) -> None:
    """A dispatch older than the window is no longer a dedup hit."""
    cell_ids = await _seed_aoi_with_cells()
    cells = [_cell(cell_ids[0], score=0.80, level=RiskLevel.VeryHigh)]
    capture = _CaptureChannel()

    # First dispatch using a 60 min window.
    await AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    ).run(_ctx(cells))
    assert await count_dispatches() == 1

    # Rewind the first row beyond the window.
    async with acquire() as conn:
        await conn.execute(
            "UPDATE alert_dispatches SET dispatched_at = now() - $1::interval",
            timedelta(hours=3),
        )

    await AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    ).run(_ctx(cells))
    assert len(capture.received) == 2
    assert await count_dispatches() == 2


async def test_dispatcher_none_still_persists(reset_db: None) -> None:
    """With no dispatcher (V1 stub fallback) we still record the dispatch."""
    cell_ids = await _seed_aoi_with_cells()
    cells = [_cell(cell_ids[0], score=0.80, level=RiskLevel.VeryHigh)]
    executor = AlertDispatchExecutor(
        dispatcher=None,
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    )
    result = await executor.run(_ctx(cells))
    assert len(result.dispatched_alerts) == 1
    persisted = await fetch_recent(aoi_id=_AOI_ID)
    assert persisted[0]["channels"] == {}


async def test_exposure_boosts_priority(reset_db: None) -> None:
    """Cell with populated exposure ranks ahead of an unexposed cell at equal score."""
    cell_ids = await _seed_aoi_with_cells()
    exposed_id, unexposed_id = cell_ids[0], cell_ids[1]
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE cell_static_factors
            SET population_count = 5000, buildings_count = 200,
                infra_density_norm = 0.8
            WHERE cell_id = $1
            """,
            exposed_id,
        )
    cells = [
        _cell(unexposed_id, score=0.80, level=RiskLevel.High),
        _cell(exposed_id, score=0.80, level=RiskLevel.High),
    ]
    capture = _CaptureChannel()
    await AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(min_level="High", dedup_window_minutes=60),
    ).run(_ctx(cells))

    payload = capture.received[0]
    # Exposed cell ranks first despite identical raw score.
    assert payload.cells[0].cell_id == exposed_id
    assert payload.cells[0].priority > payload.cells[1].priority


async def test_moderate_alerts_only_on_susceptible_slopes(reset_db: None) -> None:
    """Below-High cells pass only with S >= min_static_s (susceptible slope)."""
    cell_ids = await _seed_aoi_with_cells()
    cells = [
        _cell(cell_ids[0], score=0.40, level=RiskLevel.Moderate),  # s=0.40 < gate
        _cell(cell_ids[1], score=0.52, level=RiskLevel.Moderate),  # s=0.52 >= gate
    ]
    capture = _CaptureChannel()
    executor = AlertDispatchExecutor(
        dispatcher=NotificationDispatcher([capture]),
        alert_settings=AlertSettings(
            min_level="Moderate", min_static_s=0.5, dedup_window_minutes=60
        ),
    )
    result = await executor.run(_ctx(cells))

    assert len(capture.received) == 1
    flagged = {c.cell_id for c in capture.received[0].cells}
    assert flagged == {cell_ids[1]}
    assert result.dispatched_alerts
