"""Antecedent Precipitation Index (Kohler-Linsley) unit tests."""

from __future__ import annotations

import pytest

from limen.core.scoring.api import _sigmoid, api_factor, api_kohler_linsley
from limen.core.scoring.regional_thresholds import load_regional_thresholds


@pytest.fixture(scope="module")
def thresholds():  # type: ignore[no-untyped-def]
    return load_regional_thresholds()


def test_api_zero_when_no_rain() -> None:
    assert api_kohler_linsley([0.0, 0.0, 0.0], decay_k=0.9) == 0.0


def test_api_increases_with_daily_rain() -> None:
    api = api_kohler_linsley([10.0, 20.0, 5.0], decay_k=0.9)
    # API_1 = 10, API_2 = 0.9*10 + 20 = 29, API_3 = 0.9*29 + 5 = 31.1
    assert api == pytest.approx(31.1, rel=1e-9)


def test_api_rejects_invalid_decay() -> None:
    with pytest.raises(ValueError, match="decay_k"):
        api_kohler_linsley([10.0], decay_k=1.5)


def test_api_rejects_negative_precip() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        api_kohler_linsley([-1.0], decay_k=0.9)


def test_api_factor_none_returns_neutral(thresholds) -> None:
    assert api_factor(None, api=thresholds.api) == 0.5


def test_api_factor_increases_with_value(thresholds) -> None:
    """Monotonically non-decreasing in API magnitude (sigmoid)."""
    lo = api_factor(20.0, api=thresholds.api)
    mid = api_factor(thresholds.api.baseline.fallback_mm, api=thresholds.api)
    hi = api_factor(200.0, api=thresholds.api)
    assert lo < mid < hi
    assert mid == pytest.approx(0.5, abs=1e-6)


def test_api_factor_uses_explicit_baseline(thresholds) -> None:
    """An explicit (per-cell) baseline overrides the fallback."""
    api_val = 80.0
    high_baseline = api_factor(api_val, api=thresholds.api, baseline_mm=120.0)
    low_baseline = api_factor(api_val, api=thresholds.api, baseline_mm=40.0)
    assert low_baseline > high_baseline


def test_sigmoid_centred_at_zero() -> None:
    assert _sigmoid(0.0) == pytest.approx(0.5)
    assert _sigmoid(100.0) == pytest.approx(1.0)
    assert _sigmoid(-100.0) == pytest.approx(0.0)
