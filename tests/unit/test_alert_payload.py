"""AlertPayload builder + level helper unit tests (no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.config.settings import AlertSettings
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel
from limen.notifications.base import build_alert_payload, level_at_least
from tests.factories import flood_record, landslide_record


def _cell(cell_id: str, *, score: float, level: RiskLevel) -> CellRiskRecord:
    return landslide_record(cell_id, score=score, level=level, s=score, m=score)


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


# --- cascate cross-hazard nel payload (#58) ---------------------------------


def _flood_assessment(top: list[CellRiskRecord]) -> AggregateAssessment:
    a = _assessment(top)
    return a.model_copy(update={"hazard_type": HazardType.FLOOD})


def _settings() -> AlertSettings:
    return AlertSettings(
        min_level="High",
        dedup_window_minutes=60,
        top_k=5,
        map_base_url="http://map.test",
    )


def test_cascade_note_when_alerted_cells_have_burnt() -> None:
    cells = [
        flood_record(
            "aoi|0|0",
            score=0.7,
            level=RiskLevel.High,
            susceptibility=0.9,
            pluvial=0.78,
            post_fire_multiplier=1.55,
            months_since_fire=4.0,
        ),
        flood_record(
            "aoi|0|1",
            score=0.6,
            level=RiskLevel.High,
            susceptibility=0.9,
            pluvial=0.66,
            post_fire_multiplier=1.2,
            months_since_fire=11.0,
        ),
        flood_record("aoi|0|2", score=0.58, level=RiskLevel.High, susceptibility=0.8),
    ]
    payload = build_alert_payload(
        assessment=_flood_assessment(cells),
        prioritised=[(c, 1.0) for c in cells],
        settings=_settings(),
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )
    assert len(payload.cascade) == 1
    note = payload.cascade[0]
    assert note.rule == "post_fire_flood"
    # Solo le due bruciate, non tutte e tre le celle allertate.
    assert note.cells == 2
    assert "4-11 mesi fa" in note.detail_it


def test_no_cascade_note_without_a_multiplier() -> None:
    """Il campo esiste sempre e resta vuoto: non è un opzionale da dedurre."""
    cells = [flood_record("aoi|0|0", score=0.6, level=RiskLevel.High, susceptibility=0.8)]
    payload = build_alert_payload(
        assessment=_flood_assessment(cells),
        prioritised=[(cells[0], 1.0)],
        settings=_settings(),
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )
    assert payload.cascade == []


def test_landslide_alerts_carry_no_cascade_note() -> None:
    cells = [_cell("aoi|0|0", score=0.7, level=RiskLevel.High)]
    payload = build_alert_payload(
        assessment=_assessment(cells),
        prioritised=[(cells[0], 1.0)],
        settings=_settings(),
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )
    assert payload.cascade == []


def test_cascade_note_reaches_the_webhook_body() -> None:
    """Il webhook serializza il payload intero: il campo arriva al gateway."""
    cells = [
        flood_record(
            "aoi|0|0",
            score=0.7,
            level=RiskLevel.High,
            susceptibility=0.9,
            pluvial=0.78,
            post_fire_multiplier=1.4,
            months_since_fire=5.0,
        )
    ]
    payload = build_alert_payload(
        assessment=_flood_assessment(cells),
        prioritised=[(cells[0], 1.0)],
        settings=_settings(),
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )
    body = payload.model_dump(mode="json")
    assert body["hazard_type"] == "flood"
    assert body["cascade"][0]["rule"] == "post_fire_flood"
    assert body["cascade"][0]["cells"] == 1
