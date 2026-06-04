"""V2 — drift detection primitives + retraining trigger truth table."""

from __future__ import annotations

import pytest

from limen.ml.monitoring.drift import (
    DriftReport,
    ks_distance,
    make_report,
    population_stability_index,
    prediction_drift,
)
from limen.ml.monitoring.trigger import RetrainingTrigger


# ---------------------------------------------------------------------------
# PSI
# ---------------------------------------------------------------------------
def test_psi_zero_for_identical_distributions() -> None:
    ref = [0.1 * i for i in range(100)]
    cand = list(ref)
    assert population_stability_index(ref, cand) < 0.01


def test_psi_positive_for_shifted_distribution() -> None:
    ref = [0.1 * i for i in range(100)]
    cand = [v + 5.0 for v in ref]  # shift right by 5 → all mass in tail
    psi = population_stability_index(ref, cand)
    assert psi > 0.5


def test_psi_handles_empty_inputs() -> None:
    assert population_stability_index([], [1.0]) == 0.0
    assert population_stability_index([1.0], []) == 0.0


# ---------------------------------------------------------------------------
# KS
# ---------------------------------------------------------------------------
def test_ks_zero_for_identical() -> None:
    samples = [float(i) for i in range(50)]
    assert ks_distance(samples, samples) == pytest.approx(0.0)


def test_ks_large_for_disjoint() -> None:
    a = [float(i) for i in range(50)]
    b = [float(i) + 1000.0 for i in range(50)]
    assert ks_distance(a, b) > 0.8


# ---------------------------------------------------------------------------
# Prediction drift
# ---------------------------------------------------------------------------
def test_prediction_drift_is_absolute_mean_diff() -> None:
    assert prediction_drift([0.5, 0.5], [0.7, 0.7]) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# make_report + RetrainingTrigger
# ---------------------------------------------------------------------------
def test_report_marks_alerts_when_thresholds_breached() -> None:
    report = make_report(
        reference=[0.0, 0.0, 0.0, 0.0, 0.0],
        candidate=[1.0, 1.0, 1.0, 1.0, 1.0],
        reference_probs=[0.1, 0.1, 0.1],
        candidate_probs=[0.9, 0.9, 0.9],
        psi_alert=0.1,
        ks_alert=0.1,
        pred_alert=0.1,
    )
    assert report.psi_alert
    assert report.ks_alert
    assert report.pred_alert
    assert report.any_alert


def test_trigger_fires_on_psi() -> None:
    drift = DriftReport(
        psi=0.5,
        ks=0.0,
        pred_drift=0.0,
        psi_alert=True,
        ks_alert=False,
        pred_alert=False,
    )
    trig = RetrainingTrigger.from_inputs(drift=drift, new_iffi_since_last_train=0)
    assert trig.should_retrain is True
    assert "PSI" in trig.reason


def test_trigger_fires_on_new_events() -> None:
    drift = DriftReport(
        psi=0.0,
        ks=0.0,
        pred_drift=0.0,
        psi_alert=False,
        ks_alert=False,
        pred_alert=False,
    )
    trig = RetrainingTrigger.from_inputs(
        drift=drift, new_iffi_since_last_train=200, new_iffi_threshold=50
    )
    assert trig.should_retrain is True


def test_trigger_does_not_fire_when_quiet() -> None:
    drift = DriftReport(
        psi=0.05,
        ks=0.05,
        pred_drift=0.02,
        psi_alert=False,
        ks_alert=False,
        pred_alert=False,
    )
    trig = RetrainingTrigger.from_inputs(drift=drift, new_iffi_since_last_train=0)
    assert trig.should_retrain is False
