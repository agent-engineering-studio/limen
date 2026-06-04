"""V1.5 — schemas + QC pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.config.settings import IotSettings
from limen.integrations.iot.qc import (
    QcQuality,
    check_flatline,
    check_gap,
    check_range,
    check_spike_step,
    check_unit,
    run_qc,
)
from limen.integrations.iot.schemas import Observation, ObservedProperty

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _obs(
    *,
    prop: ObservedProperty = ObservedProperty.RAINFALL,
    value: float = 5.0,
    unit: str | None = None,
    ts: datetime | None = None,
) -> Observation:
    return Observation(
        thing_id="t-1",
        observed_property=prop,
        phenomenon_time=ts or NOW,
        result_value=value,
        result_unit=unit if unit is not None else _canonical_unit(prop),
    )


def _canonical_unit(prop: ObservedProperty) -> str:
    from limen.integrations.iot.schemas import CANONICAL_UNITS

    return CANONICAL_UNITS[prop]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_observation_requires_timezone() -> None:
    with pytest.raises(ValueError):
        Observation(
            thing_id="t-1",
            observed_property=ObservedProperty.RAINFALL,
            phenomenon_time=datetime(2026, 6, 1, 12, 0),
            result_value=5.0,
            result_unit="mm",
        )


def test_observation_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        Observation.model_validate(
            {
                "thing_id": "t-1",
                "observed_property": "rainfall",
                "phenomenon_time": NOW.isoformat(),
                "result_value": 5.0,
                "result_unit": "mm",
                "stowaway": True,
            }
        )


def test_canonical_unit_property() -> None:
    o = _obs(prop=ObservedProperty.VELOCITY)
    assert o.canonical_unit == "mm/d"


# ---------------------------------------------------------------------------
# QC — individual checks
# ---------------------------------------------------------------------------
def test_check_unit_flags_mismatch() -> None:
    obs = _obs(prop=ObservedProperty.DISPLACEMENT, value=1.0, unit="m")
    assert check_unit(obs) is QcQuality.UNIT


def test_check_range_detects_out_of_bounds() -> None:
    settings = IotSettings()
    obs_bad = _obs(value=settings.qc_rainfall_range[1] + 1.0)
    assert check_range(obs_bad, settings) is QcQuality.RANGE


def test_check_range_accepts_in_bounds() -> None:
    settings = IotSettings()
    obs = _obs(value=10.0)
    assert check_range(obs, settings) is QcQuality.OK


def test_check_spike_step_fires_on_large_step() -> None:
    settings = IotSettings()
    obs = _obs(prop=ObservedProperty.VELOCITY, value=100.0)
    # 100 mm/d vs previous 1 mm/d at sigma=3 mm/d, factor=5 → threshold 15.
    assert (
        check_spike_step(obs, previous_value=1.0, sigma=3.0, settings=settings) is QcQuality.SPIKE
    )


def test_check_spike_step_no_previous_is_ok() -> None:
    settings = IotSettings()
    obs = _obs(value=999.0)
    assert check_spike_step(obs, previous_value=None, sigma=3.0, settings=settings) is QcQuality.OK


def test_check_flatline_requires_full_window() -> None:
    settings = IotSettings()
    obs = _obs(value=5.0)
    # Not enough samples → OK.
    assert check_flatline(obs, [5.0, 5.0], settings) is QcQuality.OK
    # Same value across the whole window → flatline.
    repeats = [5.0] * (settings.flatline_min_samples - 1)
    assert check_flatline(obs, repeats, settings) is QcQuality.FLATLINE


def test_check_gap_fires_on_long_silence() -> None:
    settings = IotSettings()
    obs = _obs(ts=NOW)
    long_ago = NOW - timedelta(minutes=settings.gap_threshold_minutes + 5)
    assert check_gap(obs, long_ago, settings) is QcQuality.GAP


# ---------------------------------------------------------------------------
# QC — run_qc returns the worst label
# ---------------------------------------------------------------------------
def test_run_qc_picks_the_worst_label() -> None:
    settings = IotSettings()
    bad = _obs(
        prop=ObservedProperty.VELOCITY,
        value=settings.qc_velocity_range[1] + 100.0,
        unit="m/d",
    )
    quality = run_qc(
        bad,
        previous_value=None,
        previous_timestamp=None,
        recent_values=[],
        sigma=3.0,
        settings=settings,
    )
    # UNIT is the most severe of the firing checks (UNIT > RANGE).
    assert quality is QcQuality.UNIT


def test_run_qc_ok_when_everything_passes() -> None:
    settings = IotSettings()
    obs = _obs(value=5.0)
    assert (
        run_qc(
            obs,
            previous_value=5.0,
            previous_timestamp=NOW - timedelta(minutes=10),
            recent_values=[5.0, 4.5, 4.8],
            sigma=3.0,
            settings=settings,
        )
        is QcQuality.OK
    )
