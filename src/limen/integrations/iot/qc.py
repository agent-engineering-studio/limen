"""Quality control for incoming sensor observations.

Each check returns the :class:`QcQuality` it would assign — the
combined :func:`run_qc` keeps the worst quality (with ``ok`` as the
neutral element). The ingestor stores the resulting label on the
``sensor_observations.quality`` column and feeds it back into the
rollup: only ``ok`` rows contribute to the engine's K component.

Four checks, in order of severity:

* :func:`check_range`      — value outside the property's physical bounds.
* :func:`check_spike_step` — step change from the previous sample exceeds
  ``spike_step_factor * sigma_v`` (V1.5 spec).
* :func:`check_flatline`   — N consecutive identical readings inside a
  configurable window.
* :func:`check_gap`        — time since the previous sample exceeds the
  configured threshold.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from enum import StrEnum

from limen.config.settings import IotSettings
from limen.integrations.iot.schemas import Observation, ObservedProperty


class QcQuality(StrEnum):
    """Severity-ordered quality classes (`ok` is best, `unit` worst).

    The enum order mirrors the SQL CHECK constraint in
    ``009_sensor_tables.sql`` so a quality label round-trips through
    the database unchanged.
    """

    OK = "ok"
    GAP = "gap"
    FLATLINE = "flatline"
    SPIKE = "spike"
    RANGE = "range"
    UNIT = "unit"


_SEVERITY: dict[QcQuality, int] = {
    QcQuality.OK: 0,
    QcQuality.GAP: 1,
    QcQuality.FLATLINE: 2,
    QcQuality.SPIKE: 3,
    QcQuality.RANGE: 4,
    QcQuality.UNIT: 5,
}


def _worse(a: QcQuality, b: QcQuality) -> QcQuality:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def _range_for(prop: ObservedProperty, settings: IotSettings) -> tuple[float, float]:
    match prop:
        case ObservedProperty.RAINFALL:
            return settings.qc_rainfall_range
        case ObservedProperty.PORE_PRESSURE:
            return settings.qc_pore_pressure_range
        case ObservedProperty.SOIL_MOISTURE:
            return settings.qc_soil_moisture_range
        case ObservedProperty.DISPLACEMENT:
            return settings.qc_displacement_range
        case ObservedProperty.VELOCITY:
            return settings.qc_velocity_range
        case ObservedProperty.ACCELERATION:
            return settings.qc_acceleration_range


def check_unit(observation: Observation) -> QcQuality:
    """Flag observations whose unit doesn't match the canonical UCUM code.

    The ingestor's calibration step is the right place to convert from
    a compatible unit (e.g. ``m`` → ``mm``); this check fires when the
    payload arrives *uncalibrated* and the result_unit still differs.
    """
    if observation.result_unit.strip() != observation.canonical_unit:
        return QcQuality.UNIT
    return QcQuality.OK


def check_range(observation: Observation, settings: IotSettings) -> QcQuality:
    lo, hi = _range_for(observation.observed_property, settings)
    if not (lo <= observation.result_value <= hi):
        return QcQuality.RANGE
    return QcQuality.OK


def check_spike_step(
    observation: Observation,
    previous_value: float | None,
    *,
    sigma: float,
    settings: IotSettings,
) -> QcQuality:
    """Single-sample step check.

    ``sigma`` is the property-specific noise scale — the YAML's
    ``kinematic.sigma_v`` is the canonical source for displacement/
    velocity; for meteo properties the caller can pass a sensible
    fallback (e.g. measurement resolution).
    """
    if previous_value is None or sigma <= 0:
        return QcQuality.OK
    if abs(observation.result_value - previous_value) > settings.spike_step_factor * sigma:
        return QcQuality.SPIKE
    return QcQuality.OK


def check_flatline(
    observation: Observation,
    recent_values: Sequence[float],
    settings: IotSettings,
) -> QcQuality:
    """Flag N identical samples inside a window.

    ``recent_values`` is the trailing window of previous observations of
    the same datastream (in the order they were observed). The current
    observation is treated as the *most recent* — callers should NOT
    include it in ``recent_values``.
    """
    needed = settings.flatline_min_samples - 1
    if needed <= 0 or len(recent_values) < needed:
        return QcQuality.OK
    tail = recent_values[-needed:]
    if all(v == observation.result_value for v in tail):
        return QcQuality.FLATLINE
    return QcQuality.OK


def check_gap(
    observation: Observation,
    previous_timestamp: datetime | None,
    settings: IotSettings,
) -> QcQuality:
    if previous_timestamp is None:
        return QcQuality.OK
    if observation.phenomenon_time - previous_timestamp > timedelta(
        minutes=settings.gap_threshold_minutes
    ):
        return QcQuality.GAP
    return QcQuality.OK


def run_qc(
    observation: Observation,
    *,
    previous_value: float | None,
    previous_timestamp: datetime | None,
    recent_values: Sequence[float],
    sigma: float,
    settings: IotSettings,
) -> QcQuality:
    """Compose the four checks and return the worst label.

    The order is unit → range → spike → flatline → gap, but the
    *severity* ordering (not the call order) is what selects the final
    label.
    """
    quality = QcQuality.OK
    quality = _worse(quality, check_unit(observation))
    quality = _worse(quality, check_range(observation, settings))
    quality = _worse(
        quality,
        check_spike_step(observation, previous_value, sigma=sigma, settings=settings),
    )
    quality = _worse(quality, check_flatline(observation, recent_values, settings))
    quality = _worse(quality, check_gap(observation, previous_timestamp, settings))
    return quality


__all__ = [
    "QcQuality",
    "check_flatline",
    "check_gap",
    "check_range",
    "check_spike_step",
    "check_unit",
    "run_qc",
]
