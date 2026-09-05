"""Forecast-trend persistence — pure selection logic (issue #41)."""

from __future__ import annotations

from limen.agents.workflows.forecast_history import at_or_above, cells_to_persist
from limen.core.models.context import CellRiskRecord
from limen.core.models.risk import RiskLevel
from tests.factories import landslide_record


def _cell(cell_id: str, level: RiskLevel, score: float) -> CellRiskRecord:
    return landslide_record(cell_id, score=score, level=level, s=0.1, m=0.1)


def test_at_or_above_ordering() -> None:
    assert at_or_above(RiskLevel.Moderate, RiskLevel.Moderate) is True
    assert at_or_above(RiskLevel.High, RiskLevel.Moderate) is True
    assert at_or_above(RiskLevel.Low, RiskLevel.Moderate) is False
    assert at_or_above(RiskLevel.None_, RiskLevel.Moderate) is False


def test_cells_to_persist_keeps_only_moderate_plus() -> None:
    cells = [
        _cell("a", RiskLevel.None_, 0.1),
        _cell("b", RiskLevel.Low, 0.2),
        _cell("c", RiskLevel.Moderate, 0.4),
        _cell("d", RiskLevel.VeryHigh, 0.9),
    ]
    kept = cells_to_persist(cells)
    assert [c.cell_id for c in kept] == ["c", "d"]
