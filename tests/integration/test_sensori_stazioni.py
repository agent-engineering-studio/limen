"""Le stazioni sulla mappa pubblica (#255): mai la posizione esatta di un privato."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shapely.geometry import Point

from limen.core import sensori_stazioni
from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos import sensor_devices_repo
from limen.data.repos.sensor_devices_repo import SensorDevice
from limen.integrations.iot.partitions import ensure_partition_window

pytestmark = pytest.mark.integration


async def _osserva(device_id: str, grandezza: str, unita: str, quando: datetime, qc: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_observations
                (device_id, observed_property, phenomenon_time, result_value, result_unit, quality)
            VALUES ($1, $2, $3, 0.4, $4, $5)
            """,
            device_id,
            grandezza,
            quando,
            unita,
            qc,
        )


async def test_le_stazioni_dei_privati_escono_arrotondate(reset_db: None) -> None:
    adesso = datetime.now(UTC)
    async with acquire() as conn:
        await ensure_partition_window(conn, reference=adesso.date(), window_months=1)
        rid = await conn.fetchval(
            "INSERT INTO sensori_registranti (email) VALUES ('a@esempio.it') RETURNING id"
        )
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id="pluvio-casa-01",
                device_type="pluviometro",
                cell_id=None,
                location=Point(16.123456, 40.987654),
                calibration={},
                livello=0,
            ),
            SensorDevice(
                id="arpa-umido-01",
                device_type="soil_moisture",
                cell_id=None,
                location=Point(15.555555, 40.444444),
                calibration={},
                livello=2,
            ),
            SensorDevice(
                id="nuovo-01",
                device_type="pluviometro",
                cell_id=None,
                location=Point(16.5, 41.5),
                calibration={},
                livello=0,
            ),
        ]
    )
    async with acquire() as conn:
        await conn.execute(
            "UPDATE sensor_devices SET registrante_id = $1 WHERE id = 'pluvio-casa-01'", rid
        )
    await _osserva("pluvio-casa-01", "rainfall", "mm", adesso - timedelta(hours=1), "ok")
    await _osserva("pluvio-casa-01", "rainfall", "mm", adesso - timedelta(minutes=5), "spike")
    await _osserva("arpa-umido-01", "soil_moisture", "m3/m3", adesso - timedelta(hours=2), "ok")

    stazioni = {s.id: s for s in await sensor_devices_repo.stazioni_pubbliche()}

    privata = stazioni["pluvio-casa-01"]
    assert (privata.lon, privata.lat) == (16.12, 40.99)
    assert privata.arrotondata
    assert privata.ultima_grandezza == "rainfall"
    # L'ultima riga è un picco scartato: l'ultimo dato è quella prima.
    assert privata.ultimo_istante is not None
    assert privata.ultimo_istante < adesso - timedelta(minutes=30)
    assert (privata.valide_24h, privata.segnalate_24h) == (1, 1)
    # L'ente resta dov'è.
    ente = stazioni["arpa-umido-01"]
    assert (ente.lon, ente.lat) == (15.555555, 40.444444)
    assert not ente.arrotondata

    def ids(hazard: HazardType | None) -> set[str]:
        fc = sensori_stazioni.geojson(list(stazioni.values()), hazard)
        return {f["properties"]["id"] for f in fc["features"]}

    assert ids(None) == {"pluvio-casa-01", "arpa-umido-01", "nuovo-01"}
    assert ids(HazardType.FLOOD) == {"pluvio-casa-01", "nuovo-01"}
    assert ids(HazardType.LANDSLIDE) == {"pluvio-casa-01", "arpa-umido-01", "nuovo-01"}
    # L'incendio non legge nessuna grandezza: nessuna stazione, nemmeno le mute.
    assert ids(HazardType.WILDFIRE) == set()

    # Revocato (o cancellato su richiesta): sparisce dalla mappa.
    await sensor_devices_repo.set_status("nuovo-01", "quarantined")
    assert "nuovo-01" not in {s.id for s in await sensor_devices_repo.stazioni_pubbliche()}

    proprieta = sensori_stazioni.geojson([privata], None)["features"][0]["properties"]
    assert "registrante_id" not in proprieta
    assert "email" not in str(proprieta)
