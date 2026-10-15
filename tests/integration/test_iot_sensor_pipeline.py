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

from limen.agents.executors.sensor_fetch import SensorFetchExecutor
from limen.core.models.context import MonitoringContext
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

_MAX_AGE = timedelta(minutes=120)


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
                livello=2,
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
                livello=2,
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

    row = await sensor_features_hourly_repo.latest_for_cell(
        cell_id, as_of=bucket + timedelta(hours=1), max_age=_MAX_AGE
    )
    assert row is not None
    assert row.velocity_mmd is not None
    # 5 mm/h ≈ 120 mm/d, allow for the regression's endpoint inclusion.
    assert row.velocity_mmd == pytest.approx(120.0, rel=0.05)
    # 6 samples fall inside the half-open [11:00, 12:00) bucket window.
    assert row.sample_count == 6


async def test_livello_roundtrip(reset_db: None) -> None:
    cell_id = await _seed_aoi_and_cells()
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="pluvio-cittadino",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=0,
            ),
            SensorDevice(
                id="pluvio-ente",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.89, 41.14),
                calibration={},
                livello=2,
            ),
            SensorDevice(
                id="pluvio-senza-livello",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.89, 41.15),
                calibration={},
            ),
        ]
    )
    cittadino = await sensor_devices_repo.get_device("pluvio-cittadino")
    ente = await sensor_devices_repo.get_device("pluvio-ente")
    assert cittadino is not None and cittadino.livello == 0
    assert ente is not None and ente.livello == 2
    # Chi non dichiara il livello resta fuori dallo scoring, anche in SQL.
    senza = await sensor_devices_repo.get_device("pluvio-senza-livello")
    assert senza is not None and senza.livello == 0
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO sensor_devices (id, device_type, location) "
            "VALUES ('grezzo', 'rain_gauge', ST_SetSRID(ST_MakePoint(16.9, 41.15), 4326))"
        )
        assert await conn.fetchval("SELECT livello FROM sensor_devices WHERE id = 'grezzo'") == 0

    # Un re-sync dell'anagrafica non cambia il livello: né in su né in giù.
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="pluvio-cittadino",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={"rainfall": {"scale": 1.0, "offset": 0.0}},
                livello=2,
            ),
            SensorDevice(
                id="pluvio-ente",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.89, 41.14),
                calibration={"rainfall": {"scale": 1.0, "offset": 0.0}},
            ),
        ]
    )
    cittadino = await sensor_devices_repo.get_device("pluvio-cittadino")
    ente = await sensor_devices_repo.get_device("pluvio-ente")
    assert cittadino is not None and cittadino.livello == 0
    assert ente is not None and ente.livello == 2


def _pioggia(device_id: str, bucket: datetime, mm: float) -> list[SensorObservation]:
    return [
        SensorObservation(
            device_id=device_id,
            observed_property=ObservedProperty.RAINFALL,
            phenomenon_time=bucket + timedelta(minutes=i * 10),
            result_value=mm,
            result_unit="mm",
            raw_value=mm,
            quality=QcQuality.OK,
        )
        for i in range(6)
    ]


def _frana_in_accelerazione(device_id: str, bucket: datetime) -> list[SensorObservation]:
    return [
        SensorObservation(
            device_id=device_id,
            observed_property=ObservedProperty.DISPLACEMENT,
            phenomenon_time=bucket + timedelta(minutes=i * 10),
            result_value=10.0 + i * i * 4.0,
            result_unit="mm",
            raw_value=None,
            quality=QcQuality.OK,
        )
        for i in range(6)
    ]


async def test_rollup_ignora_i_livelli_0_e_1(reset_db: None) -> None:
    """Un pluviometro di terzi che segna zero non abbassa M, e un
    estensimetro di terzi in accelerazione non arriva a `hard_escalation`:
    nessuno dei due entra nell'aggregato che l'engine legge (#251)."""
    cell_id = await _seed_aoi_and_cells()
    async with acquire() as conn:
        altra = await conn.fetchval(
            "SELECT id FROM grid_cells WHERE aoi_id = 'aoi-iot' AND id <> $1 ORDER BY id LIMIT 1",
            cell_id,
        )
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="pluvio-ente",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=2,
            ),
            SensorDevice(
                id="pluvio-intasato",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=0,
            ),
            SensorDevice(
                id="estensimetro-urtato",
                device_type="extensometer",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=1,
            ),
            SensorDevice(
                id="pluvio-solo-cittadino",
                device_type="rain_gauge",
                cell_id=altra,
                location=Point(16.90, 41.15),
                calibration={},
                livello=1,
            ),
        ]
    )
    bucket = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
    await sensor_observations_repo.insert_many(
        _pioggia("pluvio-ente", bucket, 2.0)
        + _pioggia("pluvio-intasato", bucket, 0.0)
        + _frana_in_accelerazione("estensimetro-urtato", bucket)
        + _pioggia("pluvio-solo-cittadino", bucket, 30.0)
    )

    written = await run_hourly_rollup(reference=bucket + timedelta(minutes=30))
    assert written == 1

    row = await sensor_features_hourly_repo.latest_for_cell(
        cell_id, as_of=bucket + timedelta(hours=1), max_age=_MAX_AGE
    )
    assert row is not None
    assert row.rainfall_mm == pytest.approx(12.0)
    assert row.sample_count == 6
    assert row.displacement_mm is None
    assert row.velocity_mmd is None
    assert row.acceleration_mmd2 is None
    # Una cella con soli dispositivi di terzi resta sul modello: al bundle
    # non arriva niente, quindi score, breakdown e hard_escalation sono
    # quelli V1 (test_v15_disabled_matches_v1).
    assert (
        await sensor_features_hourly_repo.latest_for_cell(
            altra, as_of=bucket + timedelta(hours=1), max_age=_MAX_AGE
        )
        is None
    )
    ctx = await SensorFetchExecutor(max_age=_MAX_AGE).run(
        MonitoringContext(
            aoi_id="aoi-iot",
            valuation_time=bucket + timedelta(hours=1),
            cell_ids=(cell_id, altra),
        )
    )
    assert set(ctx.sensor_features_by_cell) == {cell_id}

    # Le osservazioni grezze restano: servono a verifiche e promozione.
    async with acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM sensor_observations WHERE device_id = 'pluvio-intasato'"
        )
    assert n == 6


async def test_un_dato_vecchio_non_e_piu_una_misura(reset_db: None) -> None:
    """Un pluviometro che ha segnato zero e poi tace non tiene M bassa per
    sempre, e un replay non legge le misure di dopo (#262)."""
    cell_id = await _seed_aoi_and_cells()
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="pluvio-ente",
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=2,
            )
        ]
    )
    bucket = datetime(2026, 6, 1, 11, 0, tzinfo=UTC)
    await sensor_observations_repo.insert_many(_pioggia("pluvio-ente", bucket, 0.0))
    await run_hourly_rollup(reference=bucket + timedelta(minutes=30))
    ultima = bucket + timedelta(minutes=50)

    async def letta(as_of: datetime) -> bool:
        row = await sensor_features_hourly_repo.latest_for_cell(
            cell_id, as_of=as_of, max_age=_MAX_AGE
        )
        return row is not None

    assert await letta(ultima + timedelta(minutes=30))
    assert await letta(ultima + _MAX_AGE - timedelta(minutes=1))
    assert not await letta(ultima + _MAX_AGE)
    assert not await letta(ultima + timedelta(days=3))
    # Replay alle 11:30: l'ultima osservazione (11:50) non è ancora avvenuta.
    assert not await letta(bucket + timedelta(minutes=30))
