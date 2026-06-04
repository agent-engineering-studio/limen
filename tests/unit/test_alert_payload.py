"""AlertPayload builder + level helper unit tests (no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.config.settings import AlertSettings
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.risk import (
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
)
from limen.notifications.base import build_alert_payload, level_at_least


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


def _assessment(top: list[CellRiskRecord]) -> AggregateAssessment:
    return AggregateAssessment(
        aoi_id="it-puglia",
        model_version="limen-deterministic-v1",
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        n_cells=len(top),
        cells_high_or_above=sum(1 for c in top if c.level in {RiskLevel.High, RiskLevel.VeryHigh}),
        cells_by_level={"High": sum(1 for c in top if c.level == RiskLevel.High)},
        top_cells=top,
    )


def test_level_at_least_orders_classes() -> None:
    assert level_at_least(RiskLevel.High, RiskLevel.High)
    assert level_at_least(RiskLevel.VeryHigh, RiskLevel.High)
    assert not level_at_least(RiskLevel.Moderate, RiskLevel.High)
    assert not level_at_least(RiskLevel.None_, RiskLevel.Low)


def test_payload_includes_top_k_cells_and_map_links() -> None:
    cells = [
        _cell("aoi|0|0", score=0.82, level=RiskLevel.VeryHigh),
        _cell("aoi|0|1", score=0.65, level=RiskLevel.High),
        _cell("aoi|0|2", score=0.62, level=RiskLevel.High),
    ]
    a = _assessment(cells)
    settings = AlertSettings(
        min_level="High",
        dedup_window_minutes=60,
        top_k=2,
        map_base_url="http://map.test",
    )
    now = datetime(2026, 6, 1, 12, 30, tzinfo=UTC)

    payload = build_alert_payload(
        assessment=a,
        prioritised=[(c, c.score * 1.5) for c in cells],
        settings=settings,
        dispatched_at=now,
    )

    assert payload.aoi_id == "it-puglia"
    assert payload.max_level == RiskLevel.VeryHigh
    assert payload.max_score == pytest.approx(0.82)
    assert len(payload.cells) == 2  # top_k cap
    assert payload.cells[0].cell_id == "aoi|0|0"
    assert payload.cells[0].map_url is not None
    assert "cell=aoi%7C0%7C0" in payload.cells[0].map_url
    assert payload.map_url is not None
    assert "aoi=it-puglia" in payload.map_url
    assert payload.pipeline_version == "v1-deterministic"


def test_summary_is_within_80_words_and_mentions_aoi() -> None:
    cells = [_cell("aoi|0|0", score=0.7, level=RiskLevel.High)]
    payload = build_alert_payload(
        assessment=_assessment(cells),
        prioritised=[(cells[0], 0.7)],
        settings=AlertSettings(),
        dispatched_at=datetime.now(UTC),
    )
    word_count = len(payload.summary_it.split())
    assert word_count <= 80
    assert "it-puglia" in payload.summary_it
    # No invented figures: every number in the summary appears in the
    # assessment (score 0.70 is a transformation of cells[0].score).
    assert "0.70" in payload.summary_it


def test_payload_handles_empty_prioritised() -> None:
    payload = build_alert_payload(
        assessment=_assessment([]),
        prioritised=[],
        settings=AlertSettings(),
        dispatched_at=datetime.now(UTC),
    )
    assert payload.cell_count == 0
    assert payload.max_level == RiskLevel.None_
    assert payload.max_score == 0.0
