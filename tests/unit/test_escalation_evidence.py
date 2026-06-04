"""Escalation sub-workflow — evidence bundle is pure + deterministic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.agents.workflows.escalation_workflow import (
    EscalationEvidence,
    build_escalation_evidence,
)
from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)


def _record(
    *,
    cell_id: str,
    level: RiskLevel,
    score: float,
    s: float = 0.0,
    m: float = 0.0,
    e: float = 0.0,
    f: float = 0.0,
    h: float = 0.0,
    k: float = 0.0,
    hard_escalation: bool = False,
) -> CellRiskRecord:
    return CellRiskRecord(
        cell_id=cell_id,
        score=score,
        level=level,
        static_terms=StaticBreakdown(
            susc_ispra=0.0, iffi_density=0.0, slope=0.0, pai=0.0, litho_weight=0.0
        ),
        meteo_terms=MeteoBreakdown(
            caine_excess=0.0, caine_norm=0.0, api_factor=0.0, soil_factor=0.0
        ),
        s=s,
        m=m,
        e=e,
        f=f,
        h=h,
        k=k,
        hard_escalation=hard_escalation,
    )


def _ctx(records: list[CellRiskRecord]) -> MonitoringContext:
    return MonitoringContext(
        aoi_id="aoi-test",
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        cell_results=records,
    )


def test_empty_when_no_cell_is_escalated() -> None:
    ctx = _ctx(
        [
            _record(cell_id="c-1", level=RiskLevel.Low, score=0.1),
            _record(cell_id="c-2", level=RiskLevel.Moderate, score=0.3),
        ]
    )
    assert build_escalation_evidence(ctx) == []


def test_high_cells_surface_in_evidence() -> None:
    ctx = _ctx(
        [
            _record(cell_id="c-1", level=RiskLevel.High, score=0.7, m=0.6),
            _record(cell_id="c-2", level=RiskLevel.Low, score=0.1),
            _record(cell_id="c-3", level=RiskLevel.VeryHigh, score=0.9, e=0.7),
        ]
    )
    out = build_escalation_evidence(ctx)
    # Sorted descending by score: VeryHigh first, then High.
    assert [r.cell_id for r in out] == ["c-3", "c-1"]
    assert all(isinstance(r, EscalationEvidence) for r in out)


def test_hard_escalation_bypasses_level_threshold() -> None:
    """A Low-level cell with hard_escalation=True still surfaces."""
    ctx = _ctx(
        [
            _record(
                cell_id="kinematic-alarm",
                level=RiskLevel.Low,
                score=0.2,
                k=0.85,
                hard_escalation=True,
            ),
            _record(cell_id="quiet", level=RiskLevel.Low, score=0.1),
        ]
    )
    out = build_escalation_evidence(ctx)
    assert [r.cell_id for r in out] == ["kinematic-alarm"]
    assert out[0].hard_escalation is True
    assert out[0].dominant_component == "K"


def test_dominant_component_picks_highest_contribution() -> None:
    ctx = _ctx(
        [_record(cell_id="meteo-driven", level=RiskLevel.High, score=0.7, s=0.2, m=0.6, e=0.1)]
    )
    out = build_escalation_evidence(ctx)
    assert out[0].dominant_component == "M"


def test_top_k_is_respected() -> None:
    records = [
        _record(cell_id=f"c-{i}", level=RiskLevel.High, score=0.7 + i * 0.001) for i in range(10)
    ]
    out = build_escalation_evidence(_ctx(records), top_k=3)
    assert len(out) == 3
    # Highest 3 scores must be picked (descending).
    scores = [r.score for r in out]
    assert scores == sorted(scores, reverse=True)


def test_top_k_validates() -> None:
    with pytest.raises(ValueError):
        build_escalation_evidence(_ctx([]), top_k=0)


def test_pure_function_no_side_effects() -> None:
    """Calling the function twice on the same input returns identical bundles."""
    ctx = _ctx(
        [
            _record(cell_id="c-1", level=RiskLevel.High, score=0.71, m=0.5, e=0.3),
            _record(cell_id="c-2", level=RiskLevel.VeryHigh, score=0.95, s=0.7),
        ]
    )
    a = build_escalation_evidence(ctx)
    b = build_escalation_evidence(ctx)
    assert a == b
