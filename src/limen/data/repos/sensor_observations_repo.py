"""Raw sensor-observation stream.

Writes go to the partitioned :sql:`sensor_observations` table (the
parent — PostgreSQL routes to the right monthly partition). Reads
support the QC hot-path (the previous value + the trailing N readings
for a given datastream) and the rollup job (a window scan per cell).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.iot.qc import QcQuality
from limen.integrations.iot.schemas import ObservedProperty

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SensorObservation:
    device_id: str
    observed_property: ObservedProperty
    phenomenon_time: datetime
    result_value: float
    result_unit: str
    raw_value: float | None
    quality: QcQuality
    metadata: dict[str, Any] | None = None


async def insert(observation: SensorObservation) -> None:
    """Insert one observation (single-row hot path used by the ingestor)."""
    metadata_json = json.dumps(observation.metadata or {}, default=str)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_observations (
                device_id, observed_property, phenomenon_time,
                result_value, result_unit, raw_value, quality, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
            """,
            observation.device_id,
            observation.observed_property.value,
            observation.phenomenon_time,
            observation.result_value,
            observation.result_unit,
            observation.raw_value,
            observation.quality.value,
            metadata_json,
        )


async def insert_many(observations: Iterable[SensorObservation]) -> int:
    obs_list = list(observations)
    if not obs_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for obs in obs_list:
            metadata_json = json.dumps(obs.metadata or {}, default=str)
            await conn.execute(
                """
                INSERT INTO sensor_observations (
                    device_id, observed_property, phenomenon_time,
                    result_value, result_unit, raw_value, quality, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """,
                obs.device_id,
                obs.observed_property.value,
                obs.phenomenon_time,
                obs.result_value,
                obs.result_unit,
                obs.raw_value,
                obs.quality.value,
                metadata_json,
            )
    return len(obs_list)


@dataclass(frozen=True, slots=True)
class RecentSample:
    phenomenon_time: datetime
    result_value: float


async def latest_for_datastream(
    device_id: str,
    observed_property: ObservedProperty,
) -> RecentSample | None:
    """Most recent observation (any quality) — used by QC step/gap checks."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT phenomenon_time, result_value
            FROM sensor_observations
            WHERE device_id = $1 AND observed_property = $2
            ORDER BY phenomenon_time DESC
            LIMIT 1
            """,
            device_id,
            observed_property.value,
        )
    if row is None:
        return None
    return RecentSample(
        phenomenon_time=row["phenomenon_time"],
        result_value=float(row["result_value"]),
    )


async def recent_values(
    device_id: str,
    observed_property: ObservedProperty,
    *,
    limit: int,
) -> list[float]:
    """Trailing ``limit`` raw values in chronological order (oldest → newest)."""
    if limit <= 0:
        return []
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT result_value
            FROM (
                SELECT phenomenon_time, result_value
                FROM sensor_observations
                WHERE device_id = $1 AND observed_property = $2
                ORDER BY phenomenon_time DESC
                LIMIT $3
            ) AS t
            ORDER BY phenomenon_time ASC
            """,
            device_id,
            observed_property.value,
            limit,
        )
    return [float(r["result_value"]) for r in rows]


@dataclass(frozen=True, slots=True)
class DisplacementSample:
    phenomenon_time: datetime
    result_value: float


async def displacement_window(
    device_id: str,
    *,
    since: datetime,
    until: datetime,
) -> list[DisplacementSample]:
    """OK-quality displacement samples used by the rollup velocity estimator."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT phenomenon_time, result_value
            FROM sensor_observations
            WHERE device_id = $1
              AND observed_property = $2
              AND quality = 'ok'
              AND phenomenon_time >= $3
              AND phenomenon_time <  $4
            ORDER BY phenomenon_time ASC
            """,
            device_id,
            ObservedProperty.DISPLACEMENT.value,
            since,
            until,
        )
    return [
        DisplacementSample(
            phenomenon_time=r["phenomenon_time"],
            result_value=float(r["result_value"]),
        )
        for r in rows
    ]


__all__ = [
    "DisplacementSample",
    "RecentSample",
    "SensorObservation",
    "displacement_window",
    "insert",
    "insert_many",
    "latest_for_datastream",
    "recent_values",
]
