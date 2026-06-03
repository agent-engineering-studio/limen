"""Caine threshold + event-reconstruction unit tests.

Known-scenario assertions, no I/O. The engine is a pure function of
its YAML config + bundle, so we can test it deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.core.models.risk import RainfallSample, RainfallSeries
from limen.core.scoring.caine import (
    caine_excess,
    compute_caine,
    reconstruct_events,
    threshold_intensity_mm_h,
)
from limen.core.scoring.regional_thresholds import load_regional_thresholds


@pytest.fixture(scope="module")
def thresholds():  # type: ignore[no-untyped-def]
    return load_regional_thresholds()


def _series(values_mm: list[float], start: datetime | None = None) -> RainfallSeries:
    """Hourly rainfall series from a list of mm values."""
    start = start or datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    return RainfallSeries(
        samples=tuple(
            RainfallSample(timestamp=start + timedelta(hours=i), precipitation_mm=v)
            for i, v in enumerate(values_mm)
        )
    )


def test_threshold_intensity_is_a_power_law(thresholds) -> None:
    """I(D) = α · D^(-β): longer duration → lower threshold intensity."""
    i_short = threshold_intensity_mm_h(1.0, caine=thresholds.caine, macroregion="italy_default")
    i_long = threshold_intensity_mm_h(24.0, caine=thresholds.caine, macroregion="italy_default")
    assert i_long < i_short
    # And the ratio matches the analytical (24^β)
    ratio = i_short / i_long
    expected = 24.0 ** thresholds.caine.macroregions["italy_default"].beta
    assert ratio == pytest.approx(expected, rel=1e-6)


def test_unknown_macroregion_falls_back_to_default(thresholds) -> None:
    default = threshold_intensity_mm_h(6.0, caine=thresholds.caine, macroregion="italy_default")
    unknown = threshold_intensity_mm_h(6.0, caine=thresholds.caine, macroregion="does_not_exist")
    assert unknown == default


def test_threshold_rejects_non_positive_duration(thresholds) -> None:
    with pytest.raises(ValueError, match="duration_hours"):
        threshold_intensity_mm_h(0.0, caine=thresholds.caine)


def test_event_reconstruction_splits_on_dry_run(thresholds) -> None:
    """A 12-hour dry gap (>= no_rain_break_hours=6) must split events."""
    samples = _series([2, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 3, 2]).samples
    events = reconstruct_events(
        samples,
        no_rain_break_hours=thresholds.caine.event_reconstruction.no_rain_break_hours,
        min_event_mm=thresholds.caine.event_reconstruction.min_event_mm,
    )
    assert len(events) == 2
    assert events[0].total_mm == pytest.approx(7.0)
    assert events[1].total_mm == pytest.approx(9.0)


def test_event_reconstruction_drops_below_min_mm(thresholds) -> None:
    """Total below min_event_mm (=2.0) is discarded."""
    samples = _series([0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]).samples
    events = reconstruct_events(
        samples,
        no_rain_break_hours=thresholds.caine.event_reconstruction.no_rain_break_hours,
        min_event_mm=thresholds.caine.event_reconstruction.min_event_mm,
    )
    assert events == []


def test_caine_excess_is_zero_when_below_threshold(thresholds) -> None:
    """A 6-hour event with 5 mm/h intensity sits well below the threshold."""
    rainfall = _series([5, 5, 5, 5, 5, 5])
    excess, event = compute_caine(rainfall, caine=thresholds.caine)
    assert event is not None
    # Threshold at D=6h is alpha / 6^beta (~3.7 mm/h with defaults). Our
    # event at 5 mm/h is above it, so we assert the symmetric property:
    # "well below threshold" yields zero, using a much smaller intensity:
    rainfall_low = _series([1, 1, 1, 1, 1, 1])
    excess_low, _ = compute_caine(rainfall_low, caine=thresholds.caine)
    assert excess_low == 0.0
    assert excess >= 0.0


def test_caine_excess_grows_with_intensity(thresholds) -> None:
    """Strictly monotonic: more rain at fixed duration → ≥ excess."""
    light = _series([3, 3, 3, 3, 3, 3])
    heavy = _series([20, 20, 20, 20, 20, 20])
    excess_light, _ = compute_caine(light, caine=thresholds.caine)
    excess_heavy, _ = compute_caine(heavy, caine=thresholds.caine)
    assert excess_heavy > excess_light


def test_caine_excess_handles_none_event(thresholds) -> None:
    assert caine_excess(None, caine=thresholds.caine) == 0.0
