"""Post-fire amplification window unit tests."""

from __future__ import annotations

import pytest

from limen.core.scoring.post_fire import post_fire_factor
from limen.core.scoring.regional_thresholds import load_regional_thresholds


@pytest.fixture(scope="module")
def thresholds():  # type: ignore[no-untyped-def]
    return load_regional_thresholds()


def test_no_fire_yields_zero(thresholds) -> None:
    assert post_fire_factor(None, post_fire=thresholds.post_fire) == 0.0


def test_negative_months_yields_zero(thresholds) -> None:
    assert post_fire_factor(-1.0, post_fire=thresholds.post_fire) == 0.0


def test_beyond_window_yields_zero(thresholds) -> None:
    """Months > window_months_max → no amplification."""
    over = thresholds.post_fire.window_months_max + 1.0
    assert post_fire_factor(over, post_fire=thresholds.post_fire) == 0.0


def test_peak_at_six_months(thresholds) -> None:
    """The Gaussian is centred on peak_months (=6.0)."""
    f_peak = post_fire_factor(thresholds.post_fire.peak_months, post_fire=thresholds.post_fire)
    f_off = post_fire_factor(0.0, post_fire=thresholds.post_fire)
    f_late = post_fire_factor(18.0, post_fire=thresholds.post_fire)
    assert f_peak == pytest.approx(1.0)
    assert f_peak > f_off
    assert f_peak > f_late


def test_monotonic_around_peak(thresholds) -> None:
    """Moving away from the peak in either direction reduces the factor."""
    base = post_fire_factor(thresholds.post_fire.peak_months, post_fire=thresholds.post_fire)
    left = post_fire_factor(2.0, post_fire=thresholds.post_fire)
    right = post_fire_factor(12.0, post_fire=thresholds.post_fire)
    assert left < base
    assert right < base
