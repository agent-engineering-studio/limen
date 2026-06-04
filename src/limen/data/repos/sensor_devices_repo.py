"""Sensor-device (SensorThings ``Thing``) registry.

The MQTT ingestor calls :func:`get_device` to resolve a ``thing_id`` to
its cell binding + calibration. The static loader for demo deployments
uses :func:`upsert_many`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


SensorStatus = Literal["online", "offline", "quarantined"]


@dataclass(frozen=True, slots=True)
class SensorDevice:
    id: str
    device_type: str
    cell_id: str | None
    location: BaseGeometry
    calibration: dict[str, Any]
    status: SensorStatus = "online"
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] | None = None


async def upsert_many(items: Iterable[SensorDevice]) -> int:
    """Insert-or-update each device by id."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items_list:
            calibration_json = json.dumps(it.calibration or {}, default=str)
            metadata_json = json.dumps(it.metadata or {}, default=str)
            await conn.execute(
                """
                INSERT INTO sensor_devices (
                    id, device_type, cell_id, location,
                    calibration, status, last_seen_at, metadata
                ) VALUES (
                    $1, $2, $3, ST_SetSRID($4::geometry, 4326),
                    $5::jsonb, $6, $7, $8::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET device_type = EXCLUDED.device_type,
                    cell_id     = EXCLUDED.cell_id,
                    location    = EXCLUDED.location,
                    calibration = EXCLUDED.calibration,
                    status      = EXCLUDED.status,
                    last_seen_at = COALESCE(EXCLUDED.last_seen_at,
                                            sensor_devices.last_seen_at),
                    metadata    = EXCLUDED.metadata,
                    updated_at  = now()
                """,
                it.id,
                it.device_type,
                it.cell_id,
                it.location,
                calibration_json,
                it.status,
                it.last_seen_at,
                metadata_json,
            )
    log.info("sensor_devices.upsert_many", count=len(items_list))
    return len(items_list)


async def get_device(device_id: str) -> SensorDevice | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, device_type, cell_id, location,
                   calibration, status, last_seen_at, metadata
            FROM sensor_devices
            WHERE id = $1
            """,
            device_id,
        )
    if row is None:
        return None
    calibration = row["calibration"]
    if isinstance(calibration, str):
        calibration = json.loads(calibration)
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    location = row["location"]
    if not isinstance(location, BaseGeometry):
        location = Point(0.0, 0.0)
    return SensorDevice(
        id=row["id"],
        device_type=row["device_type"],
        cell_id=row["cell_id"],
        location=location,
        calibration=calibration or {},
        status=row["status"],
        last_seen_at=row["last_seen_at"],
        metadata=metadata or {},
    )


async def touch_last_seen(device_id: str, *, at: datetime) -> None:
    """Bump ``last_seen_at`` (idempotent — no-op if device is missing)."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE sensor_devices
               SET last_seen_at = GREATEST(COALESCE(last_seen_at, $2), $2),
                   updated_at = now()
             WHERE id = $1
            """,
            device_id,
            at,
        )


async def set_status(device_id: str, status: SensorStatus) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE sensor_devices SET status = $2, updated_at = now() WHERE id = $1",
            device_id,
            status,
        )


__all__ = [
    "SensorDevice",
    "SensorStatus",
    "get_device",
    "set_status",
    "touch_last_seen",
    "upsert_many",
]
