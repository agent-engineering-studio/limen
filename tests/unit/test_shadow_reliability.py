"""Reliability-curve binning — pure, no DB (#30)."""

from __future__ import annotations

from limen.ml.shadow import reliability_bins


def test_bins_drop_empties_and_compute_freq() -> None:
    # 0.05 bucket: 2 preds, 1 observed → observed_freq 0.5
    # 0.95 bucket: 2 preds, 2 observed → observed_freq 1.0
    pairs = [(0.05, False), (0.06, True), (0.95, True), (0.96, True)]
    bins = reliability_bins(pairs, n_bins=10)
    assert len(bins) == 2  # only two non-empty buckets
    low, high = bins[0], bins[1]
    assert low.count == 2 and low.observed_freq == 0.5
    assert high.count == 2 and high.observed_freq == 1.0
    assert 0.0 <= low.predicted_mean < 0.1
    assert 0.9 <= high.predicted_mean <= 1.0


def test_well_calibrated_lands_on_diagonal() -> None:
    # In each decile bucket, observed frequency ≈ bin centre → |pred - obs| small.
    pairs: list[tuple[float, bool]] = []
    for i in range(10):
        center = (i + 0.5) / 10
        # 10 samples per bucket; `round(center*10)` of them positive
        n_pos = round(center * 10)
        for j in range(10):
            pairs.append((center, j < n_pos))
    bins = reliability_bins(pairs, n_bins=10)
    assert len(bins) == 10
    for b in bins:
        assert abs(b.predicted_mean - b.observed_freq) <= 0.1


def test_edge_probabilities_clamped_into_range() -> None:
    bins = reliability_bins([(1.0, True), (0.0, False)], n_bins=10)
    assert len(bins) == 2  # p=1.0 folds into the top bucket, p=0.0 into the bottom
