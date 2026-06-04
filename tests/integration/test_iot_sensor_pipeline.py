"""Integration test for the V1.5 sensor pipeline.

Exercises the migration + the three repos + the hourly rollup against
a real PostgreSQL + PostGIS instance via testcontainers. The MQTT
ingestor's broker hop is unit-tested in ``test_iot_mqtt_ingestor`` —
this test focuses on the DB write path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shapely.geometry import Point, Polygon

from limen.data.db import acquire
from limen.data.repos import (
    aoi_repo,
    grid_repo,
    sensor_devices_repo,
    sensor_features_hourly_repo,
    sensor_observations_repo,
)
from limen.data.repos.sensor_devices_repo import SensorDevice
from limen.data.repos.sensor_observations_repo import SensorObservation
from limen.integrations.iot.qc import QcQuality
from limen.integrations.iot.rollup import run_hourly_rollup
from limen.integrations.iot.schemas import ObservedProperty

pytestmark = pytest.mark.integration


_TEST_POLY = Polygon(
    [
        (16.86, 41.12),
        (16.92, 41.12),
        (16.92, 41.17),
        (16.86, 41.17),
        (16.86, 41.12),
    ]
)


async def _seed_aoi_and_cells() -> str:
    await aoi_repo.upsert_aoi(
        id="aoi-iot",
        name="IoT integration AOI",
        kind="test",
        geom=_TEST_POLY,
        metadata={},
    )
    await grid_repo.generate_and_store_grid("aoi-iot")
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 1",
            "aoi-iot",
        )
    assert row is not None
    return str(row["id"])


async def test_sensor_repos_roundtrip(reset_db: None) -> None:
    cell_id = await _seed_aoi_and_cells()
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="thing-a",
                device_type="extensometer",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={"displacement": {"scale": 1.0, "offset": 0.0}},
            )
        ]
    )
    fetched = await sensor_devices_repo.get_device("thing-a")
    assert fetched is not None
    assert fetched.cell_id == cell_id

    bucket = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
    obs = [
        SensorObservation(
            device_id="thing-a",
            observed_property=ObservedProperty.DISPLACEMENT,
            phenomenon_time=bucket + timedelta(minutes=i * 10),
            result_value=10.0 + i * 0.5,
            result_unit="mm",
            raw_value=10.0 + i * 0.5,
            quality=QcQuality.OK,
        )
        for i in range(6)
    ]
    written = await sensor_observations_repo.insert_many(obs)
    assert written == 6

    samples = await sensor_observations_repo.displacement_window(
        "thing-a", since=bucket, until=bucket + timedelta(hours=1)
    )
    assert len(samples) == 6
    assert samples[0].result_value == pytest.approx(10.0)


async def test_hourly_rollup_writes_velocity(reset_db: None) -> None:
    cell_id = await _seed_aoi_and_cells()
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="thing-b",
                device_type="extensometer",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
            )
        ]
    )
    # Linear displacement: +5 mm/h → 120 mm/d.
    bucket = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
    obs = [
        SensorObservation(
            device_id="thing-b",
            observed_property=ObservedProperty.DISPLACEMENT,
            phenomenon_time=bucket + timedelta(minutes=i * 10),
            result_value=10.0 + i * (5.0 / 6.0),  # 5 mm over the hour
            result_unit="mm",
            raw_value=None,
            quality=QcQuality.OK,
        )
        for i in range(7)  # 7 samples spanning [00 .. 60min]
    ]
    await sensor_observations_repo.insert_many(obs)

    written = await run_hourly_rollup(reference=bucket + timedelta(minutes=30))
    assert written == 1

    row = await sensor_features_hourly_repo.latest_for_cell(cell_id)
    assert row is not None
    assert row.velocity_mmd is not None
    # 5 mm/h ≈ 120 mm/d, allow for the regression's endpoint inclusion.
    assert row.velocity_mmd == pytest.approx(120.0, rel=0.05)
    # 6 samples fall inside the half-open [11:00, 12:00) bucket window.
    assert row.sample_count == 6
