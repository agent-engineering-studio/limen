"""Hourly rollup — OK observations → ``sensor_features_hourly``.

The job groups OK-quality observations into one-hour buckets and writes
one row per (cell_id, bucket). For displacement, it derives velocity
(mm/d) by linear regression on the bucket's samples, acceleration by
finite difference between consecutive hourly velocities, and the
inverse-velocity = 1 / max(velocity, eps) (Fukuzono input).

Per §2.9, this is enough to feed the K kinematic component of the
scoring engine without storing the raw displacement series in
``sensor_features_hourly``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import structlog

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import (
    sensor_features_hourly_repo,
    sensor_observations_repo,
)
from limen.data.repos.sensor_features_hourly_repo import SensorFeaturesRow
from limen.integrations.iot.schemas import ObservedProperty

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


def _floor_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


async def _devices_with_cells() -> list[tuple[str, str]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, cell_id
            FROM sensor_devices
            WHERE cell_id IS NOT NULL
              AND status = 'online'
            """,
        )
    return [(r["id"], r["cell_id"]) for r in rows]


async def _meteo_aggregates_for(
    device_id: str,
    *,
    bucket_start: datetime,
    bucket_end: datetime,
    observed_property: ObservedProperty,
) -> tuple[float | None, int, datetime | None]:
    """Mean of OK samples in the bucket, count, last-observation-at."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT AVG(result_value) AS avg_value,
                   COUNT(*)::int     AS n,
                   MAX(phenomenon_time) AS last_at
            FROM sensor_observations
            WHERE device_id = $1
              AND observed_property = $2
              AND quality = 'ok'
              AND phenomenon_time >= $3
              AND phenomenon_time <  $4
            """,
            device_id,
            observed_property.value,
            bucket_start,
            bucket_end,
        )
    if row is None or row["n"] == 0:
        return None, 0, None
    return float(row["avg_value"]), int(row["n"]), row["last_at"]


async def _sum_rainfall_for(
    device_id: str,
    *,
    bucket_start: datetime,
    bucket_end: datetime,
) -> tuple[float | None, int, datetime | None]:
    """Rainfall accumulates — sum (not mean) in the bucket."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT SUM(result_value) AS total,
                   COUNT(*)::int     AS n,
                   MAX(phenomenon_time) AS last_at
            FROM sensor_observations
            WHERE device_id = $1
              AND observed_property = $2
              AND quality = 'ok'
              AND phenomenon_time >= $3
              AND phenomenon_time <  $4
            """,
            device_id,
            ObservedProperty.RAINFALL.value,
            bucket_start,
            bucket_end,
        )
    if row is None or row["n"] == 0:
        return None, 0, None
    return float(row["total"]), int(row["n"]), row["last_at"]


def _linear_velocity_mmd(samples: list[tuple[datetime, float]]) -> float | None:
    """Least-squares slope on the (t, displacement) samples → mm/day.

    Needs at least 2 samples. Returns None when the time span collapses.
    """
    if len(samples) < 2:
        return None
    t0 = samples[0][0]
    xs = [(s[0] - t0).total_seconds() / 86_400.0 for s in samples]  # days
    ys = [s[1] for s in samples]
    n = float(len(samples))
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys, strict=True))
    sum_xx = sum(x * x for x in xs)
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0.0:
        return None
    return (n * sum_xy - sum_x * sum_y) / denom


async def _previous_velocity_for(
    device_id: str,
    *,
    bucket_start: datetime,
) -> float | None:
    """Most recent prior hourly velocity for this device's cell.

    Used to derive acceleration as finite difference between hourly
    velocities. Falls back to None if there's no prior bucket.
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT f.velocity_mmd
            FROM sensor_devices d
            JOIN sensor_features_hourly f ON f.cell_id = d.cell_id
            WHERE d.id = $1
              AND f.bucket < $2
              AND f.velocity_mmd IS NOT NULL
            ORDER BY f.bucket DESC
            LIMIT 1
            """,
            device_id,
            bucket_start,
        )
    if row is None or row["velocity_mmd"] is None:
        return None
    return float(row["velocity_mmd"])


async def _rollup_device_bucket(
    *,
    device_id: str,
    cell_id: str,
    bucket_start: datetime,
    bucket_end: datetime,
) -> SensorFeaturesRow | None:
    """Compute the (cell_id, bucket) row contributed by ONE device."""
    rainfall_mm, rainfall_n, rainfall_last = await _sum_rainfall_for(
        device_id, bucket_start=bucket_start, bucket_end=bucket_end
    )
    pore_kpa, pore_n, pore_last = await _meteo_aggregates_for(
        device_id,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        observed_property=ObservedProperty.PORE_PRESSURE,
    )
    soil, soil_n, soil_last = await _meteo_aggregates_for(
        device_id,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        observed_property=ObservedProperty.SOIL_MOISTURE,
    )

    disp_samples = await sensor_observations_repo.displacement_window(
        device_id, since=bucket_start, until=bucket_end
    )
    displacement_mm: float | None = None
    velocity_mmd: float | None = None
    last_disp_at: datetime | None = None
    if disp_samples:
        displacement_mm = disp_samples[-1].result_value
        last_disp_at = disp_samples[-1].phenomenon_time
        velocity_mmd = _linear_velocity_mmd(
            [(s.phenomenon_time, s.result_value) for s in disp_samples]
        )

    acceleration_mmd2: float | None = None
    if velocity_mmd is not None:
        prev_v = await _previous_velocity_for(device_id, bucket_start=bucket_start)
        if prev_v is not None:
            # one hour = 1/24 day, so accel in mm/d² is (v - v_prev) / (1/24).
            acceleration_mmd2 = (velocity_mmd - prev_v) * 24.0

    inverse_velocity: float | None = None
    if velocity_mmd is not None and velocity_mmd > 1e-6:
        inverse_velocity = 1.0 / velocity_mmd

    sample_count = rainfall_n + pore_n + soil_n + len(disp_samples)
    if sample_count == 0:
        return None

    last_at_candidates = [
        x for x in (rainfall_last, pore_last, soil_last, last_disp_at) if x is not None
    ]
    last_observation_at = max(last_at_candidates) if last_at_candidates else None

    return SensorFeaturesRow(
        cell_id=cell_id,
        bucket=bucket_start,
        rainfall_mm=rainfall_mm,
        pore_pressure_kpa=pore_kpa,
        soil_moisture=soil,
        displacement_mm=displacement_mm,
        velocity_mmd=velocity_mmd,
        acceleration_mmd2=acceleration_mmd2,
        inverse_velocity=inverse_velocity,
        sample_count=sample_count,
        last_observation_at=last_observation_at,
    )


async def run_hourly_rollup(*, reference: datetime) -> int:
    """Roll the hour that contains ``reference`` into the per-cell features.

    Returns the number of (cell_id, bucket) rows written. Idempotent —
    re-running on the same hour merges via the COALESCE upsert in
    :mod:`sensor_features_hourly_repo`.
    """
    bucket_start = _floor_to_hour(reference)
    bucket_end = bucket_start + timedelta(hours=1)
    devices = await _devices_with_cells()
    if not devices:
        _log.info("iot.rollup.no_devices")
        return 0

    by_cell: dict[str, SensorFeaturesRow] = {}
    for device_id, cell_id in devices:
        row = await _rollup_device_bucket(
            device_id=device_id,
            cell_id=cell_id,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
        )
        if row is None:
            continue
        if cell_id in by_cell:
            by_cell[cell_id] = by_cell[cell_id].merged_with(row)
        else:
            by_cell[cell_id] = row

    for row in by_cell.values():
        await sensor_features_hourly_repo.upsert(row)

    _log.info(
        "iot.rollup.done",
        bucket=bucket_start.isoformat(),
        devices=len(devices),
        cells=len(by_cell),
    )
    return len(by_cell)


__all__ = ["run_hourly_rollup"]
