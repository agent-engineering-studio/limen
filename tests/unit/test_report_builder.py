from limen.core.models.risk import RiskLevel
from limen.report.builder import (
    _threshold_candidates,
    _zones_notice,
    assessment_signature,
    build_id_for,
)


def test_signature_is_stable_and_order_independent() -> None:
    a = {"cells": [{"cell_id": "a", "score": 0.5}, {"cell_id": "b", "score": 0.9}]}
    b = {"cells": [{"cell_id": "b", "score": 0.9}, {"cell_id": "a", "score": 0.5}]}
    assert assessment_signature(a) == assessment_signature(b)


def test_build_id_from_valuation_time() -> None:
    assert build_id_for("2026-07-11T08:00:00+00:00") == "2026-07-11T0800Z"


def test_threshold_candidates_steps_down_from_alert_to_low() -> None:
    assert _threshold_candidates(RiskLevel.High) == [
        RiskLevel.High,
        RiskLevel.Moderate,
        RiskLevel.Low,
    ]
    assert _threshold_candidates(RiskLevel.VeryHigh)[0] == RiskLevel.VeryHigh
    assert _threshold_candidates(RiskLevel.VeryHigh)[-1] == RiskLevel.Low
    # a level already at the floor has no lower rungs
    assert _threshold_candidates(RiskLevel.Low) == [RiskLevel.Low]


def test_zones_notice_none_when_zones_meet_alert_level() -> None:
    assert (
        _zones_notice(alert_level=RiskLevel.High, shown_level=RiskLevel.High, has_clusters=True)
        is None
    )


def test_zones_notice_flags_below_alert_as_informational() -> None:
    msg = _zones_notice(
        alert_level=RiskLevel.High, shown_level=RiskLevel.Moderate, has_clusters=True
    )
    assert msg is not None
    assert "soglia di allerta" in msg
    assert "nessun allarme" in msg.lower()


def test_zones_notice_when_no_zones_at_all() -> None:
    msg = _zones_notice(alert_level=RiskLevel.High, shown_level=RiskLevel.High, has_clusters=False)
    assert msg is not None
    assert "Nessuna zona a rischio" in msg


def test_zones_notice_reports_diffuse_tail_alongside_hotspots() -> None:
    msg = _zones_notice(
        alert_level=RiskLevel.High,
        shown_level=RiskLevel.High,
        has_clusters=True,
        diffuse_cells=5280,
    )
    assert msg is not None
    assert "5280" in msg


def test_zones_notice_diffuse_only_when_no_net_hotspot() -> None:
    # Regione uniforme: hotspot azzerati dalla salienza ma migliaia di celle
    # diffuse — non deve dire "nessuna zona a rischio", deve riportare il diffuso.
    msg = _zones_notice(
        alert_level=RiskLevel.High,
        shown_level=RiskLevel.Moderate,
        has_clusters=False,
        diffuse_cells=5280,
    )
    assert msg is not None
    assert "5280" in msg
    assert "Nessuna zona a rischio" not in msg
