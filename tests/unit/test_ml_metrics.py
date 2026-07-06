"""V2 — promotion-gate metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.ml.metrics import auc_pr, brier_score, hit_rate_far, mean_lead_time_hours


def test_auc_pr_perfect_classifier() -> None:
    pytest.importorskip("sklearn")
    assert auc_pr([0, 0, 1, 1], [0.1, 0.2, 0.9, 0.95]) == pytest.approx(1.0)


def test_brier_score_perfect_calibration() -> None:
    pytest.importorskip("sklearn")
    assert brier_score([0, 1], [0.0, 1.0]) == pytest.approx(0.0)


def test_hit_rate_far_simple() -> None:
    pytest.importorskip("numpy")
    y_true = [1, 1, 0, 0]
    y_prob = [0.9, 0.8, 0.1, 0.4]
    hit_rate, far = hit_rate_far(y_true, y_prob, threshold=0.5)
    assert hit_rate == pytest.approx(1.0)
    assert far == pytest.approx(0.0)


def test_lead_time_average() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    vts = [base, base + timedelta(hours=2)]
    events = [base + timedelta(hours=12), base + timedelta(hours=24)]
    hits = [True, True]
    assert mean_lead_time_hours(vts, events, hits=hits) == pytest.approx(17.0)


def test_lead_time_ignores_misses() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    vts = [base, base + timedelta(hours=2)]
    events = [base + timedelta(hours=12), base + timedelta(hours=24)]
    hits = [True, False]
    assert mean_lead_time_hours(vts, events, hits=hits) == pytest.approx(12.0)


def test_tss_perfect_classifier() -> None:
    from limen.ml.metrics import tss

    y = [0, 0, 1, 1]
    p = [0.1, 0.2, 0.8, 0.9]
    skill, sens, spec = tss(y, p, threshold=0.5)
    assert (skill, sens, spec) == (1.0, 1.0, 1.0)


def test_threshold_sweep_meets_recall_targets() -> None:
    from limen.ml.metrics import threshold_sweep

    y = [1] * 10 + [0] * 90
    p = [i / 10 for i in range(10, 0, -1)] + [0.05] * 90
    points = threshold_sweep(y, p, recall_targets=(0.5, 0.9))
    for point in points:
        assert point["hit_rate"] >= point["recall_target"]
    assert points[0]["threshold"] > points[1]["threshold"]


def test_conformal_quantiles_cover_marginally() -> None:
    from limen.ml.metrics import conformal_quantiles

    y = [0] * 90 + [1] * 10
    p = [0.05] * 90 + [0.7] * 10
    q = conformal_quantiles(y, p)
    assert set(q) == {"q80", "q90", "q95"}
    assert q["q80"] <= q["q90"] <= q["q95"]
    covered = sum(1 for yt, yp in zip(y, p) if abs(yt - yp) <= q["q90"])
    assert covered / len(y) >= 0.9
