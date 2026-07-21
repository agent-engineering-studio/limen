"""AlertedCell carries an optional comune (payload enrichment)."""

from __future__ import annotations

from limen.core.models.risk import RiskLevel
from limen.notifications.base import AlertedCell


def test_alerted_cell_optional_comune() -> None:
    a = AlertedCell(cell_id="c1", score=0.8, level=RiskLevel.High, priority=1.0)
    assert a.comune is None
    b = AlertedCell(cell_id="c1", score=0.8, level=RiskLevel.High, priority=1.0, comune="Testville")
    assert b.comune == "Testville"
