"""Seismic decay + factor unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.core.models.risk import SeismicHistoryEvent
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.core.scoring.seismic_decay import compute_seismic, pga_local, seismic_factor


@pytest.fixture(scope="module")
def thresholds():  # type: ignore[no-untyped-def]
    return load_regional_thresholds()


def _event(*, days_ago: float, magnitude: float, pga_g: float) -> SeismicHistoryEvent:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    return SeismicHistoryEvent(
        event_id=f"ev-{days_ago}",
        origin_time=now - timedelta(days=days_ago),
        magnitude=magnitude,
        distance_km=10.0,
        pga_g=pga_g,
    )


def test_pga_local_is_zero_without_events(thresholds) -> None:
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    assert pga_local([], as_of=as_of, seismic=thresholds.seismic) == 0.0


def test_pga_local_decays_with_age(thresholds) -> None:
    """Same event further in the past → smaller decayed PGA."""
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    fresh = _event(days_ago=0.0, magnitude=4.5, pga_g=0.12)
    old = _event(days_ago=4.0, magnitude=4.5, pga_g=0.12)
    pga_fresh = pga_local([fresh], as_of=as_of, seismic=thresholds.seismic)
    pga_old = pga_local([old], as_of=as_of, seismic=thresholds.seismic)
    assert pga_fresh > pga_old > 0.0


def test_pga_local_drops_below_magnitude_threshold(thresholds) -> None:
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    small = _event(days_ago=0.0, magnitude=2.5, pga_g=0.10)  # below min_magnitude=3.5
    assert pga_local([small], as_of=as_of, seismic=thresholds.seismic) == 0.0


def test_pga_local_drops_beyond_lookback(thresholds) -> None:
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    old = _event(days_ago=30.0, magnitude=5.0, pga_g=0.20)  # > lookback_days=7
    assert pga_local([old], as_of=as_of, seismic=thresholds.seismic) == 0.0


def test_seismic_factor_zero_below_threshold(thresholds) -> None:
    """Local PGA below pga_threshold_g (=0.05) yields effectively low E."""
    assert seismic_factor(0.0, seismic=thresholds.seismic) == 0.0


def test_seismic_factor_grows_with_pga(thresholds) -> None:
    """E is monotonically non-decreasing in pga_local."""
    low = seismic_factor(0.06, seismic=thresholds.seismic)
    high = seismic_factor(0.30, seismic=thresholds.seismic)
    assert high > low > 0.0
    assert 0.0 <= low <= 1.0 <= 1.0 + 1e-9
    assert high <= 1.0


def test_compute_seismic_returns_pair(thresholds) -> None:
    as_of = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    pga, e = compute_seismic(
        [_event(days_ago=1.0, magnitude=4.2, pga_g=0.15)],
        as_of=as_of,
        seismic=thresholds.seismic,
    )
    assert pga > 0.0
    assert 0.0 < e <= 1.0
