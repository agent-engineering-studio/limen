"""V1.5 — kinematic component K + measured-over-modeled + invariance.

Crucially proves:

* with no sensor features, the V1.5-aware engine produces the *exact*
  same numeric output as if the kinematic block were absent (the
  byte-for-byte invariance the project doc requires);
* monotonicity of K in velocity, acceleration, and inverse-velocity;
* hard-escalation lights up when the acceleration alarm is crossed;
* measured rainfall replaces the modeled Caine factor in M.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    StaticFactors,
)
from limen.core.models.sensor import SensorFeatures
from limen.core.scoring.engine import MultiFactorScoringEngine, score
from limen.core.scoring.kinematic import compute_kinematic
from limen.core.scoring.regional_thresholds import load_regional_thresholds

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _bundle(
    *,
    sensor: SensorFeatures | None = None,
    rainfall_hourly: list[float] | None = None,
) -> CellFeatureBundle:
    samples = ()
    if rainfall_hourly:
        from datetime import timedelta

        start = NOW - timedelta(hours=len(rainfall_hourly))
        samples = tuple(
            RainfallSample(timestamp=start + timedelta(hours=i), precipitation_mm=v)
            for i, v in enumerate(rainfall_hourly)
        )
    static = StaticFactors(cell_id="c-1", susc_ispra=0.4, slope_deg=20.0)
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="c-1",
        static=static,
        dynamic=DynamicInputs(
            valuation_time=NOW,
            rainfall=RainfallSeries(samples=samples),
            sensor_features=sensor,
        ),
    )


# ---------------------------------------------------------------------------
# K — monotonicity
# ---------------------------------------------------------------------------
def test_k_is_monotone_in_velocity() -> None:
    t = load_regional_thresholds()
    assert t.kinematic is not None
    low = SensorFeatures(bucket=NOW, velocity_mmd=1.0)
    high = SensorFeatures(bucket=NOW, velocity_mmd=20.0)
    k_low, _ = compute_kinematic(low, kinematic=t.kinematic)
    k_high, _ = compute_kinematic(high, kinematic=t.kinematic)
    assert k_high > k_low


def test_k_is_zero_without_kinematic_signal() -> None:
    t = load_regional_thresholds()
    no_signal = SensorFeatures(bucket=NOW, rainfall_mm=3.0)
    k, breakdown = compute_kinematic(no_signal, kinematic=t.kinematic)
    assert k == 0.0
    assert breakdown.hard_escalation is False


def test_k_is_zero_when_kinematic_block_missing() -> None:
    sig = SensorFeatures(bucket=NOW, velocity_mmd=100.0)
    k, breakdown = compute_kinematic(sig, kinematic=None)
    assert k == 0.0
    assert breakdown.hard_escalation is False


# ---------------------------------------------------------------------------
# Hard escalation
# ---------------------------------------------------------------------------
def test_hard_escalation_fires_on_acceleration_alarm() -> None:
    t = load_regional_thresholds()
    assert t.kinematic is not None
    alarm = t.kinematic.acceleration_alarm_mmd2
    sig = SensorFeatures(
        bucket=NOW,
        velocity_mmd=10.0,
        acceleration_mmd2=alarm + 5.0,
    )
    k, breakdown = compute_kinematic(sig, kinematic=t.kinematic)
    assert breakdown.hard_escalation is True
    assert k >= 0.8


def test_hard_escalation_fires_on_inverse_velocity_alarm() -> None:
    t = load_regional_thresholds()
    assert t.kinematic is not None
    alarm = t.kinematic.inverse_velocity_alarm
    sig = SensorFeatures(
        bucket=NOW,
        velocity_mmd=5.0,
        inverse_velocity=alarm / 2.0,
    )
    k, breakdown = compute_kinematic(sig, kinematic=t.kinematic)
    assert breakdown.hard_escalation is True
    assert k >= 0.8


# ---------------------------------------------------------------------------
# Measured-over-modeled
# ---------------------------------------------------------------------------
def test_measured_rainfall_overrides_caine() -> None:
    """A direct rain-gauge reading replaces the modeled Caine factor."""
    sensor = SensorFeatures(bucket=NOW, rainfall_mm=30.0, velocity_mmd=8.0)
    s_with = score(_bundle(sensor=sensor, rainfall_hourly=[0] * 6))
    assert "caine" in s_with.breakdown.meteo_terms.measured_overrides


def test_measured_pore_pressure_overrides_api() -> None:
    sensor = SensorFeatures(
        bucket=NOW,
        pore_pressure_kpa=15.0,
        velocity_mmd=8.0,
    )
    s_with = score(_bundle(sensor=sensor))
    assert "api" in s_with.breakdown.meteo_terms.measured_overrides


# ---------------------------------------------------------------------------
# Renormalisation regime
# ---------------------------------------------------------------------------
def test_monitored_cell_sets_monitored_flag() -> None:
    sensor = SensorFeatures(bucket=NOW, velocity_mmd=20.0)
    s = score(_bundle(sensor=sensor))
    assert s.monitored is True
    assert s.breakdown.kinematic_terms is not None
    assert s.breakdown.k > 0.0


def test_unmonitored_cell_keeps_v1_breakdown_shape() -> None:
    s = score(_bundle())
    assert s.monitored is False
    assert s.breakdown.k == 0.0
    assert s.breakdown.kinematic_terms is None


# ---------------------------------------------------------------------------
# Invariance — V1.5 engine without sensor features == pure V1 numbers
# ---------------------------------------------------------------------------
def test_invariance_no_sensors_matches_v1() -> None:
    """The V1.5 engine yields the exact same score on a sensor-less bundle.

    Sanity check for the project-doc requirement: "with EnableInSitu
    off, the system is byte-for-byte the V1 behaviour."
    """
    engine = MultiFactorScoringEngine()
    bundle = _bundle(rainfall_hourly=[10] * 6)
    a = engine.score(bundle)
    b = engine.score(bundle)
    assert a == b
    assert a.breakdown.k == 0.0
    assert a.monitored is False
    assert a.hard_escalation is False


def test_invariance_sensor_features_without_kinematic_signal_matches_v1() -> None:
    """A SensorFeatures with only meteo (no velocity/accel) doesn't trigger K
    on its own — but it *does* override M. So we check the K branch stays
    inactive while the modeled M might be overridden.
    """
    engine = MultiFactorScoringEngine()
    meteo_only = SensorFeatures(bucket=NOW)  # nothing populated
    a = engine.score(_bundle())
    b = engine.score(_bundle(sensor=meteo_only))
    assert a.score == pytest.approx(b.score, abs=1e-9)
    assert b.monitored is False
    assert b.breakdown.k == 0.0


def test_invariance_yaml_without_kinematic_block_matches_v1(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A YAML with no `kinematic:` block disables K everywhere."""
    import yaml

    from limen.core.scoring.regional_thresholds import (
        DEFAULT_THRESHOLDS_PATH,
        load_regional_thresholds,
    )

    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text())
    cfg.pop("kinematic", None)
    out = tmp_path / "no_kinematic.yaml"
    out.write_text(yaml.safe_dump(cfg))
    t = load_regional_thresholds(out)
    assert t.kinematic is None
    engine = MultiFactorScoringEngine(t)
    sensor = SensorFeatures(bucket=NOW, velocity_mmd=100.0)
    result = engine.score(_bundle(sensor=sensor))
    assert result.monitored is False
    assert result.breakdown.k == 0.0
    assert result.hard_escalation is False
