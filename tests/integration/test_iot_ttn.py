"""Webhook di The Things Network (#266) contro PostGIS vero.

Il fixture è un uplink TTN v3 com'è consegnato: metadati dei gateway compresi,
``frm_payload`` SenML CBOR con il tempo relativo all'arrivo. Deve salvare le
stesse righe dello stesso SenML via MQTT.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import weakref
from datetime import timedelta
from pathlib import Path
from typing import Any

import cbor2
import httpx
import pytest
from starlette.applications import Starlette

from limen.data.db import acquire
from limen.integrations.iot.ingestore_v2 import Esito, IngestoreV2
from limen.integrations.iot.ingresso_http import applicazione
from tests.integration.test_iot_ingestore_v2 import (
    ADESSO,
    ID,
    TOPIC,
    _cella_e_dispositivo,
    _ingestore,
    _msg,
    _righe,
)

pytestmark = pytest.mark.integration

UPLINK: dict[str, Any] = json.loads(
    (Path(__file__).parent.parent / "fixtures" / "ttn_uplink.json").read_text()
)
APP = "pluviometri-matera"
DEV_EUI = "70B3D57ED0012345"
SEGRETO = "segreto-di-prova-abbastanza-lungo"

_APP: weakref.WeakKeyDictionary[IngestoreV2, Starlette] = weakref.WeakKeyDictionary()


async def _registra_ttn(*, applicazione_ttn: str = APP, dev_eui: str = DEV_EUI) -> None:
    async with acquire() as conn:
        rid = await conn.fetchval(
            "INSERT INTO sensori_registranti (email) VALUES ('maker@example.org') "
            "ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id"
        )
        await conn.execute(
            "INSERT INTO sensori_ttn (applicazione, registrante_id, segreto_sha256) "
            "VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            applicazione_ttn,
            rid,
            hashlib.sha256(SEGRETO.encode()).digest(),
        )
        await conn.execute(
            "UPDATE sensor_devices SET dev_eui = $2, ttn_applicazione = $3, registrante_id = $4 "
            "WHERE id = $1",
            ID,
            dev_eui,
            applicazione_ttn,
            rid,
        )


async def _webhook(
    ing: IngestoreV2,
    evento: dict[str, Any] | bytes,
    *,
    segreto: str | None = SEGRETO,
) -> httpx.Response:
    app = _APP.setdefault(ing, applicazione(ing.gestisci, ing._c, adesso=lambda: ADESSO))
    corpo = evento if isinstance(evento, bytes) else json.dumps(evento).encode()
    intestazioni = {} if segreto is None else {"Authorization": f"Bearer {segreto}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://sensori"
    ) as client:
        return await client.post("/sensori/v2/ttn", content=corpo, headers=intestazioni)


def _uplink(records: list[dict[int | str, Any]] | None = None, **ids: str) -> dict[str, Any]:
    evento = copy.deepcopy(UPLINK)
    if records is not None:
        evento["uplink_message"]["frm_payload"] = base64.b64encode(cbor2.dumps(records)).decode()
    if "applicazione" in ids:
        evento["end_device_ids"]["application_ids"]["application_id"] = ids["applicazione"]
    if "dev_eui" in ids:
        evento["end_device_ids"]["dev_eui"] = ids["dev_eui"]
    return evento


async def test_un_uplink_salva_le_righe_di_mqtt(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    risposta = await _webhook(_ingestore(), UPLINK)
    assert risposta.status_code == 200
    assert risposta.json() == {"esito": "salvato"}
    via_ttn = await _righe()

    async with acquire() as conn:
        await conn.execute("DELETE FROM sensor_observations WHERE device_id = $1", ID)
        await conn.execute("UPDATE sensor_devices SET ultima_sequenza = NULL WHERE id = $1", ID)
    mqtt = _msg(1, ("rainfall", "mm", 3.5, ADESSO - timedelta(minutes=2)))
    assert await _ingestore().gestisci(topic=TOPIC, payload=mqtt) is Esito.SALVATO
    assert via_ttn == await _righe()
    assert via_ttn[0]["sequenza"] == 1


@pytest.mark.parametrize(
    "segreto",
    [None, "sbagliato", "Bearer", ""],
    ids=["senza", "sbagliato", "solo_schema", "vuoto"],
)
async def test_segreto_sbagliato_401(reset_db: None, segreto: str | None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    risposta = await _webhook(_ingestore(), UPLINK, segreto=segreto)
    assert risposta.status_code == 401
    assert await _righe() == []


async def test_il_segreto_vale_solo_per_la_sua_applicazione(reset_db: None) -> None:
    """Un segreto giusto per un'altra applicazione non parla per questo DevEUI."""
    await _cella_e_dispositivo()
    await _registra_ttn()
    async with acquire() as conn:
        rid = await conn.fetchval("SELECT id FROM sensori_registranti LIMIT 1")
        await conn.execute(
            "INSERT INTO sensori_ttn (applicazione, registrante_id, segreto_sha256) "
            "VALUES ('altra-app', $1, $2)",
            rid,
            hashlib.sha256(b"altro").digest(),
        )
    risposta = await _webhook(_ingestore(), _uplink(applicazione="altra-app"), segreto="altro")
    assert risposta.status_code == 202
    assert risposta.json() == {"esito": "sconosciuto"}
    assert await _righe() == []


async def test_dev_eui_sconosciuto_scartato(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    risposta = await _webhook(_ingestore(), _uplink(dev_eui="70B3D57ED00FFFFF"))
    assert risposta.status_code == 202
    assert risposta.json() == {"esito": "sconosciuto"}
    assert await _righe() == []


async def test_il_dev_eui_si_legge_in_minuscolo(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    risposta = await _webhook(_ingestore(), _uplink(dev_eui=DEV_EUI.lower()))
    assert risposta.status_code == 200


@pytest.mark.parametrize(
    ("records", "frm"),
    [
        ([{-2: f"{ID}/", 0: "rainfall", 1: "mm", 2: 1.0}], None),  # senza seq
        ([{-2: f"{ID}/", 0: "rainfall", 1: "mm", 2: 1.0, 99: 1}, {0: "seq", 2: 1}], None),
        ([{-2: f"{ID}/", 0: "rainfall", 1: "mm", 4: b"\x01"}, {0: "seq", 2: 1}], None),
        ([{-2: "altro-01/", 0: "rainfall", 1: "mm", 2: 1.0}, {0: "seq", 2: 1}], None),
        (None, "non base64!"),
        (None, ""),
        (None, base64.b64encode(b"\xff\xff").decode()),
    ],
    ids=[
        "senza_seq",
        "etichetta_ignota",
        "byte",
        "nome_altrui",
        "base64",
        "vuoto",
        "cbor_rotto",
    ],
)
async def test_payload_non_valido_202_e_nulla_salvato(
    reset_db: None, records: list[dict[int | str, Any]] | None, frm: str | None
) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    evento = _uplink(records)
    if frm is not None:
        evento["uplink_message"]["frm_payload"] = frm
    risposta = await _webhook(_ingestore(), evento)
    # 2xx: TTN mette in pausa un webhook che fallisce, per tutta l'applicazione.
    assert risposta.status_code == 202
    assert risposta.json() == {"esito": "malformato"}
    assert await _righe() == []


async def test_un_evento_senza_uplink_si_ignora(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    evento = copy.deepcopy(UPLINK)
    del evento["uplink_message"]
    evento["join_accept"] = {"session_key_id": "x"}
    risposta = await _webhook(_ingestore(), evento)
    assert risposta.status_code == 202
    assert risposta.json() == {"esito": "ignorato"}


@pytest.mark.parametrize(
    "corpo",
    [
        b"non json",
        b"[]",
        b'{"end_device_ids": {}}',
        json.dumps(_uplink(applicazione="App_Storta")).encode(),
    ],
    ids=["non_json", "lista", "senza_ids", "applicazione_storta"],
)
async def test_evento_illeggibile_400(reset_db: None, corpo: bytes) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    assert (await _webhook(_ingestore(), corpo)).status_code == 400


@pytest.mark.parametrize("dev_eui", [None, "xyz"], ids=["senza", "storto"])
async def test_autenticato_senza_dev_eui_202(reset_db: None, dev_eui: str | None) -> None:
    """Un evento autenticato riceve sempre un 2xx: un 400 metterebbe in pausa il
    webhook di tutta l'applicazione."""
    await _cella_e_dispositivo()
    await _registra_ttn()
    evento = copy.deepcopy(UPLINK)
    if dev_eui is None:
        del evento["end_device_ids"]["dev_eui"]
    else:
        evento["end_device_ids"]["dev_eui"] = dev_eui
    risposta = await _webhook(_ingestore(), evento)
    assert (risposta.status_code, risposta.json()) == (202, {"esito": "ignorato"})
    # Senza segreto resta un 401.
    assert (await _webhook(_ingestore(), evento, segreto=None)).status_code == 401


async def test_corpo_troppo_grande_413(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    evento = copy.deepcopy(UPLINK)
    evento["uplink_message"]["rx_metadata"] *= 500
    assert (await _webhook(_ingestore(), evento)).status_code == 413


async def test_doppione_e_quarantena(reset_db: None) -> None:
    """Il frame counter non conta: decide la seq di SenML, come per MQTT."""
    await _cella_e_dispositivo()
    await _registra_ttn()
    ing = _ingestore()
    assert (await _webhook(ing, UPLINK)).status_code == 200
    ripetuto = copy.deepcopy(UPLINK)
    ripetuto["uplink_message"]["f_cnt"] = 1  # un rejoin azzera il contatore
    risposta = await _webhook(ing, ripetuto)
    assert risposta.status_code == 202
    assert risposta.json() == {"esito": "sequenza"}

    async with acquire() as conn:
        await conn.execute("UPDATE sensor_devices SET status = 'quarantined' WHERE id = $1", ID)
    nuovo = _uplink([{-2: f"{ID}/", 0: "rainfall", 1: "mm", 2: 1.0, 6: -60}, {0: "seq", 2: 2}])
    risposta = await _webhook(ing, nuovo)
    assert risposta.json() == {"esito": "quarantena"}
    assert len(await _righe()) == 1


async def test_cancellare_il_registrante_spegne_il_webhook(reset_db: None) -> None:
    await _cella_e_dispositivo()
    await _registra_ttn()
    async with acquire() as conn:
        await conn.execute("DELETE FROM sensori_registranti")
        assert (
            await conn.fetchval("SELECT ttn_applicazione FROM sensor_devices WHERE id = $1", ID)
            is None
        )
    assert (await _webhook(_ingestore(), UPLINK)).status_code == 401
