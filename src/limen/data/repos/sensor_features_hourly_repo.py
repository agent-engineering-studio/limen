"""Per-cell hourly sensor features (V1.5).

The rollup job writes here every ``iot.rollup_minutes`` minutes;
the workflow's :class:`SensorFetchExecutor` reads here when assembling
the :class:`CellFeatureBundle`. One row per (cell_id, bucket).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from limen.core.logging import get_logger
from limen.core.models.sensor import SensorFeatures
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SensorFeaturesRow:
    cell_id: str
    bucket: datetime
    rainfall_mm: float | None = None
    pore_pressure_kpa: float | None = None
    soil_moisture: float | None = None
    displacement_mm: float | None = None
    velocity_mmd: float | None = None
    acceleration_mmd2: float | None = None
    inverse_velocity: float | None = None
    sample_count: int = 0
    last_observation_at: datetime | None = None

    def to_dto(self) -> SensorFeatures:
        return SensorFeatures(
            bucket=self.bucket,
            rainfall_mm=self.rainfall_mm,
            pore_pressure_kpa=self.pore_pressure_kpa,
            soil_moisture=self.soil_moisture,
            displacement_mm=self.displacement_mm,
            velocity_mmd=self.velocity_mmd,
            acceleration_mmd2=self.acceleration_mmd2,
            inverse_velocity=self.inverse_velocity,
            sample_count=self.sample_count,
            last_observation_at=self.last_observation_at,
        )

    def merged_with(self, other: SensorFeaturesRow) -> SensorFeaturesRow:
        """Combine two partial rows for the same (cell_id, bucket).

        Used by the rollup when multiple devices contribute to one cell:
        we keep the COALESCE semantics the DB upsert uses.
        """
        return replace(
            self,
            rainfall_mm=_coalesce(self.rainfall_mm, other.rainfall_mm),
            pore_pressure_kpa=_coalesce(self.pore_pressure_kpa, other.pore_pressure_kpa),
            soil_moisture=_coalesce(self.soil_moisture, other.soil_moisture),
            displacement_mm=_coalesce(self.displacement_mm, other.displacement_mm),
            velocity_mmd=_coalesce(self.velocity_mmd, other.velocity_mmd),
            acceleration_mmd2=_coalesce(self.acceleration_mmd2, other.acceleration_mmd2),
            inverse_velocity=_coalesce(self.inverse_velocity, other.inverse_velocity),
            sample_count=self.sample_count + other.sample_count,
            last_observation_at=_max_dt(self.last_observation_at, other.last_observation_at),
        )


def _coalesce(a: float | None, b: float | None) -> float | None:
    return a if a is not None else b


def _max_dt(a: datetime | None, b: datetime | None) -> datetime | None:
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


async def upsert(row: SensorFeaturesRow) -> None:
    """Upsert one (cell_id, bucket) row — COALESCE-merge on conflict."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_features_hourly (
                cell_id, bucket, rainfall_mm, pore_pressure_kpa, soil_moisture,
                displacement_mm, velocity_mmd, acceleration_mmd2, inverse_velocity,
                sample_count, last_observation_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (cell_id, bucket) DO UPDATE
            SET rainfall_mm        = COALESCE(EXCLUDED.rainfall_mm,
                                              sensor_features_hourly.rainfall_mm),
                pore_pressure_kpa  = COALESCE(EXCLUDED.pore_pressure_kpa,
                                              sensor_features_hourly.pore_pressure_kpa),
                soil_moisture      = COALESCE(EXCLUDED.soil_moisture,
                                              sensor_features_hourly.soil_moisture),
                displacement_mm    = COALESCE(EXCLUDED.displacement_mm,
                                              sensor_features_hourly.displacement_mm),
                velocity_mmd       = COALESCE(EXCLUDED.velocity_mmd,
                                              sensor_features_hourly.velocity_mmd),
                acceleration_mmd2  = COALESCE(EXCLUDED.acceleration_mmd2,
                                              sensor_features_hourly.acceleration_mmd2),
                inverse_velocity   = COALESCE(EXCLUDED.inverse_velocity,
                                              sensor_features_hourly.inverse_velocity),
                sample_count       = sensor_features_hourly.sample_count
                                     + EXCLUDED.sample_count,
                last_observation_at = GREATEST(
                    sensor_features_hourly.last_observation_at,
                    EXCLUDED.last_observation_at
                ),
                updated_at         = now()
            """,
            row.cell_id,
            row.bucket,
            row.rainfall_mm,
            row.pore_pressure_kpa,
            row.soil_moisture,
            row.displacement_mm,
            row.velocity_mmd,
            row.acceleration_mmd2,
            row.inverse_velocity,
            row.sample_count,
            row.last_observation_at,
        )


async def sostituisci_bucket(bucket: datetime, rows: list[SensorFeaturesRow]) -> None:
    """Riscrive per intero le righe di un'ora: quelle in ``rows`` e nient'altro.

    Il rollup ricalcola l'ora da zero a ogni giro, da tutte le osservazioni
    grezze, quindi il suo risultato è l'ora intera. Fonderlo con il giro
    precedente (COALESCE) conservava valori che non valgono più: la pioggia
    parziale di un dispositivo che poi ha mandato il resto in ritardo, o la
    misura di un dispositivo nel frattempo retrocesso o andato offline — un
    valore più basso del vero, nella direzione che rassicura (#252).
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM sensor_features_hourly WHERE bucket = $1", bucket)
        await conn.executemany(
            """
            INSERT INTO sensor_features_hourly (
                cell_id, bucket, rainfall_mm, pore_pressure_kpa, soil_moisture,
                displacement_mm, velocity_mmd, acceleration_mmd2, inverse_velocity,
                sample_count, last_observation_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            [
                (
                    r.cell_id,
                    r.bucket,
                    r.rainfall_mm,
                    r.pore_pressure_kpa,
                    r.soil_moisture,
                    r.displacement_mm,
                    r.velocity_mmd,
                    r.acceleration_mmd2,
                    r.inverse_velocity,
                    r.sample_count,
                    r.last_observation_at,
                )
                for r in rows
            ],
        )


async def latest_for_cell(
    cell_id: str, *, as_of: datetime, max_age: timedelta
) -> SensorFeaturesRow | None:
    """Most recent hourly bucket for one cell whose last observation falls in
    ``(as_of - max_age, as_of]`` (used by the workflow).

    An older row is not a measurement any more: returning it would let a
    silent device keep overriding the model (#262).
    """
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, bucket, rainfall_mm, pore_pressure_kpa, soil_moisture,
                   displacement_mm, velocity_mmd, acceleration_mmd2, inverse_velocity,
                   sample_count, last_observation_at
            FROM sensor_features_hourly
            WHERE cell_id = $1
              AND last_observation_at >  $2
              AND last_observation_at <= $3
            ORDER BY bucket DESC
            LIMIT 1
            """,
            cell_id,
            as_of - max_age,
            as_of,
        )
    if row is None:
        return None
    return SensorFeaturesRow(**dict(row))


__all__ = ["SensorFeaturesRow", "latest_for_cell", "sostituisci_bucket", "upsert"]
