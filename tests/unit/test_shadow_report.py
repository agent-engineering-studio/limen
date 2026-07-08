"""Shadow-report stat helpers — pure functions, no DB."""

from __future__ import annotations

import pytest

from limen.cli.shadow_report import _aoi_stats, _pearson


def test_pearson_basics() -> None:
    assert _pearson([0.1, 0.5, 0.9], [0.2, 0.6, 1.0]) == pytest.approx(1.0)
    assert _pearson([0.1, 0.9], [0.9, 0.1]) == pytest.approx(-1.0)
    assert _pearson([0.5], [0.5]) is None
    assert _pearson([0.5, 0.5], [0.1, 0.9]) is None  # zero variance


def test_aoi_stats_divergence_and_agreement() -> None:
    pairs = [
        {
            "cell_id": "a",
            "champion_score": 0.20,
            "probability": 0.25,
            "champion_class": "Low",
            "risk_class": "Low",
        },
        {
            "cell_id": "b",
            "champion_score": 0.60,
            "probability": 0.90,
            "champion_class": "High",
            "risk_class": "VeryHigh",
        },
    ]
    stats = _aoi_stats("puglia", pairs)
    assert stats.n == 2
    assert stats.mean_abs_div == pytest.approx((0.05 + 0.30) / 2)
    assert stats.max_abs_div == pytest.approx(0.30)
    assert stats.class_agreement == pytest.approx(0.5)
    # Most divergent cell first.
    assert stats.top_divergent[0][0] == "b"
    assert stats.top_divergent[0][3] == pytest.approx(0.30)
