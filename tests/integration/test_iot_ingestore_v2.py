"""Ingestore v2 dei sensori (#252) contro PostGIS vero.

Il broker non serve: l'identità arriva già autenticata nel topic (mTLS e ACL
sono verificati da ``make sensori-check``). Qui si prova cosa succede a un
messaggio dopo il broker — cosa si salva, cosa no, e cosa arriva al rollup.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from shapely.geometry import Point, Polygon

from limen.config.settings import IotCittadiniSettings, IotSettings
from limen.data.db import acquire
from limen.data.repos import aoi_repo, grid_repo, sensor_devices_repo, sensor_features_hourly_repo
from limen.data.repos.sensor_devices_repo import SensorDevice, SensorLivello
from limen.integrations.iot.ingestore_v2 import Esito, IngestoreV2
from limen.integrations.iot.rollup import run_hourly_rollup

pytestmark = pytest.mark.integration

ID = "pluvio-matera-01"
ADESSO = datetime(2026, 6, 1, 11, 30, tzinfo=UTC)
TOPIC = f"limen/v2/{ID}/obs"


async def _cella_e_dispositivo(*, livello: SensorLivello = 2) -> str:
    await aoi_repo.upsert_aoi(
        id="aoi-v2",
        name="v2",
        kind="test",
        geom=Polygon([(16.86, 41.12), (16.92, 41.12), (16.92, 41.17), (16.86, 41.17)]),
        metadata={},
    )
    await grid_repo.generate_and_store_grid("aoi-v2")
    async with acquire() as conn:
        cell_id = str(
            await conn.fetchval("SELECT id FROM grid_cells WHERE aoi_id = 'aoi-v2' LIMIT 1")
        )
    await sensor_devices_repo.upsert_many(
        [
            SensorDevice(
                id=ID,
                device_type="rain_gauge",
                cell_id=cell_id,
                location=Point(16.88, 41.14),
                calibration={},
                livello=livello,
            )
        ]
    )
    return cell_id


def _ingestore(**soglie: Any) -> IngestoreV2:
    return IngestoreV2(
        IotSettings(cittadini=IotCittadiniSettings(enabled=True, **soglie)),
        adesso=lambda: ADESSO,
    )


def _msg(seq: int, *misure: tuple[str, str, float, datetime]) -> bytes:
    records: list[dict[str, Any]] = [
        {"bn": f"{ID}/", "n": n, "u": u, "v": v, "t": int(t.timestamp())} for n, u, v, t in misure
    ]
    records.append({"n": "seq", "v": seq})
    return json.dumps(records).encode()


async def _righe() -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT observed_property, result_value, quality, sequenza, in_ritardo "
            "FROM sensor_observations WHERE device_id = $1 ORDER BY phenomenon_time",
            ID,
        )
    return [dict(r) for r in rows]


async def test_misura_salvata_e_nel_rollup(reset_db: None) -> None:
    cell_id = await _cella_e_dispositivo()
    ing = _ingestore()
    esito = await ing.gestisci(
        topic=TOPIC, payload=_msg(1, ("rainfall", "mm", 3.5, ADESSO - timedelta(minutes=2)))
    )
    assert esito is Esito.SALVATO
    assert await _righe() == [
        {
            "observed_property": "rainfall",
            "result_value": 3.5,
            "quality": "ok",
            "sequenza": 1,
            "in_ritardo": False,
        }
    ]
    await run_hourly_rollup(reference=ADESSO)
    row = await sensor_features_hourly_repo.latest_for_cell(
        cell_id, as_of=ADESSO, max_age=timedelta(hours=2)
    )
    assert row is not None and row.rainfall_mm == pytest.approx(3.5)


async def test_dato_arretrato_salvato_in_ritardo_e_fuori_dal_rollup(reset_db: None) -> None:
    """Il temporale che il dispositivo ha registrato senza rete: si salva,
    non si rifiuta, ma non entra nello scoring."""
    cell_id = await _cella_e_dispositivo()
    ing = _ingestore()
    arretrato = ADESSO - timedelta(minutes=25)
    esito = await ing.gestisci(topic=TOPIC, payload=_msg(7, ("rainfall", "mm", 40.0, arretrato)))
    assert esito is Esito.SALVATO
    [riga] = await _righe()
    assert riga["in_ritardo"] is True
    assert riga["quality"] == "ok"

    await run_hourly_rollup(reference=arretrato)
    assert (
        await sensor_features_hourly_repo.latest_for_cell(
            cell_id, as_of=ADESSO, max_age=timedelta(hours=2)
        )
        is None
    )


async def test_tempo_futuro_rifiutato(reset_db: None) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore(tolleranza_futuro_secondi=120)
    esito = await ing.gestisci(
        topic=TOPIC, payload=_msg(1, ("rainfall", "mm", 1.0, ADESSO + timedelta(minutes=10)))
    )
    assert esito is Esito.FUTURO
    assert await _righe() == []
    # Il messaggio rifiutato non consuma la sequenza.
    esito = await ing.gestisci(topic=TOPIC, payload=_msg(1, ("rainfall", "mm", 1.0, ADESSO)))
    assert esito is Esito.SALVATO


async def test_sequenza_che_torna_indietro_scartata(reset_db: None) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore()
    misura = ("rainfall", "mm", 1.0, ADESSO)
    assert await ing.gestisci(topic=TOPIC, payload=_msg(10, misura)) is Esito.SALVATO
    assert await ing.gestisci(topic=TOPIC, payload=_msg(10, misura)) is Esito.SEQUENZA
    assert await ing.gestisci(topic=TOPIC, payload=_msg(9, misura)) is Esito.SEQUENZA
    assert len(await _righe()) == 1


async def test_malformato_sconosciuto_e_troppo_grande(reset_db: None) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore(max_payload_bytes=256)
    assert await ing.gestisci(topic=TOPIC, payload=b'{"v": 1}') is Esito.MALFORMATO
    assert await ing.gestisci(topic=TOPIC, payload=b"x" * 300) is Esito.TROPPO_GRANDE
    assert (
        await ing.gestisci(
            topic="limen/v2/nessuno-registrato/obs",
            payload=_msg(1, ("rainfall", "mm", 1.0, ADESSO)),
        )
        is Esito.SCONOSCIUTO
    )
    assert await _righe() == []


async def test_frequenza_scarta_poi_mette_in_quarantena(reset_db: None) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore(max_messaggi_al_minuto=2, scarti_per_quarantena=3)
    esiti = [
        await ing.gestisci(topic=TOPIC, payload=_msg(seq, ("rainfall", "mm", 0.2, ADESSO)))
        for seq in range(1, 6)
    ]
    assert esiti == [
        Esito.SALVATO,
        Esito.SALVATO,
        Esito.FREQUENZA,
        Esito.FREQUENZA,
        Esito.QUARANTENA,
    ]
    device = await sensor_devices_repo.get_device(ID)
    assert device is not None and device.status == "quarantined"

    # Il dispositivo non può togliersi la quarantena da solo.
    lento = _ingestore()
    stato = await lento.gestisci(topic=f"limen/v2/{ID}/status", payload=b"online")
    assert stato is Esito.QUARANTENA
    device = await sensor_devices_repo.get_device(ID)
    assert device is not None and device.status == "quarantined"


async def test_last_will(reset_db: None) -> None:
    await _cella_e_dispositivo()
    ing = _ingestore()
    assert await ing.gestisci(topic=f"limen/v2/{ID}/status", payload=b"offline") is Esito.STATO
    device = await sensor_devices_repo.get_device(ID)
    assert device is not None and device.status == "offline"
    assert await ing.gestisci(topic=f"limen/v2/{ID}/status", payload=b"boh") is Esito.MALFORMATO


async def test_dispositivo_di_terzi_salvato_ma_fuori_dallo_scoring(reset_db: None) -> None:
    """Il v2 accetta anche un osservatore: lo scoring lo esclude il livello."""
    cell_id = await _cella_e_dispositivo(livello=0)
    ing = _ingestore()
    esito = await ing.gestisci(topic=TOPIC, payload=_msg(1, ("rainfall", "mm", 0.0, ADESSO)))
    assert esito is Esito.SALVATO
    await run_hourly_rollup(reference=ADESSO)
    assert (
        await sensor_features_hourly_repo.latest_for_cell(
            cell_id, as_of=ADESSO, max_age=timedelta(hours=2)
        )
        is None
    )
