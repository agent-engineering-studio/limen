"""Ingresso HTTP firmato dei sensori (#265) contro PostGIS vero.

Il listener non serve: l'app Starlette si prova con il trasporto ASGI di
httpx. Ciò che conta è che una firma sbagliata non salvi niente e che un
messaggio valido salvi le stesse righe che lo stesso SenML salva via MQTT.
"""

from __future__ import annotations

import base64
import json
import weakref
from datetime import timedelta

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519
from starlette.applications import Starlette

from limen.data.db import acquire
from limen.data.repos import sensor_devices_repo
from limen.integrations.iot.firma_http import messaggio_firmato
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

URL = f"/sensori/v2/{ID}/obs"
TEMPO = int(ADESSO.timestamp())

Chiave = ed25519.Ed25519PrivateKey | ec.EllipticCurvePrivateKey
_APP: weakref.WeakKeyDictionary[IngestoreV2, Starlette] = weakref.WeakKeyDictionary()


async def _registra(chiave: Chiave) -> None:
    der = chiave.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    async with acquire() as conn:
        await conn.execute("UPDATE sensor_devices SET chiave_pubblica = $2 WHERE id = $1", ID, der)


def _firma(chiave: Chiave, corpo: bytes, *, tempo: int = TEMPO, device_id: str = ID) -> str:
    msg = messaggio_firmato(device_id, tempo, corpo)
    if isinstance(chiave, ed25519.Ed25519PrivateKey):
        return base64.b64encode(chiave.sign(msg)).decode()
    return base64.b64encode(chiave.sign(msg, ec.ECDSA(hashes.SHA256()))).decode()


async def _post(
    ing: IngestoreV2, corpo: bytes, *, firma: str, tempo: int | str = TEMPO, url: str = URL
) -> httpx.Response:
    # Un'app per ingestore, come un listener in produzione: la memoria dei
    # messaggi già entrati è sua.
    app = _APP.setdefault(ing, applicazione(ing.gestisci, ing._c, adesso=lambda: ADESSO))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://sensori"
    ) as client:
        return await client.post(
            url,
            content=corpo,
            headers={
                # latin-1 come in un header vero: è come Starlette lo decodifica.
                "X-Limen-Tempo": str(tempo).encode("latin-1"),
                "X-Limen-Firma": firma,
            },
        )


def _corpo(seq: int = 1) -> bytes:
    return _msg(seq, ("rainfall", "mm", 3.5, ADESSO - timedelta(minutes=2)))


@pytest.mark.parametrize(
    "chiave",
    [ed25519.Ed25519PrivateKey.generate(), ec.generate_private_key(ec.SECP256R1())],
    ids=["ed25519", "p256"],
)
async def test_stesse_righe_di_mqtt(reset_db: None, chiave: Chiave) -> None:
    await _cella_e_dispositivo()
    await _registra(chiave)
    risposta = await _post(_ingestore(), _corpo(), firma=_firma(chiave, _corpo()))
    assert risposta.status_code == 200
    assert risposta.json() == {"esito": "salvato"}
    via_http = await _righe()

    async with acquire() as conn:
        await conn.execute("DELETE FROM sensor_observations WHERE device_id = $1", ID)
        await conn.execute("UPDATE sensor_devices SET ultima_sequenza = NULL WHERE id = $1", ID)
    assert await _ingestore().gestisci(topic=TOPIC, payload=_corpo()) is Esito.SALVATO
    assert via_http == await _righe()
    assert via_http[0]["sequenza"] == 1


@pytest.mark.parametrize(
    "caso",
    [
        "firma_altrui",
        "corpo_cambiato",
        "tempo_cambiato",
        "fuori_finestra",
        "dal_futuro",
        "tempo_non_ascii",
        "tempo_enorme",
        "illeggibile",
        "senza",
    ],
)
async def test_non_autentico_401_e_nulla_salvato(reset_db: None, caso: str) -> None:
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    await _registra(chiave)
    corpo, firma = _corpo(), _firma(chiave, _corpo())
    tempo: int | str = TEMPO
    if caso == "firma_altrui":
        firma = _firma(ed25519.Ed25519PrivateKey.generate(), corpo)
    elif caso == "corpo_cambiato":
        corpo = _msg(1, ("rainfall", "mm", 99.0, ADESSO - timedelta(minutes=2)))
    elif caso == "tempo_cambiato":
        tempo = TEMPO + 1
    elif caso == "fuori_finestra":
        tempo = TEMPO - 301
        firma = _firma(chiave, corpo, tempo=TEMPO - 301)
    elif caso == "dal_futuro":
        # Oltre la tolleranza dell'orologio (120 s), anche se dentro i 300.
        tempo = TEMPO + 200
        firma = _firma(chiave, corpo, tempo=TEMPO + 200)
    elif caso == "tempo_non_ascii":
        tempo = "²"
    elif caso == "tempo_enorme":
        tempo = int("9" * 400)
    elif caso == "illeggibile":
        firma = "non base64!"
    elif caso == "senza":
        firma = ""
    risposta = await _post(_ingestore(), corpo, firma=firma, tempo=tempo)
    assert risposta.status_code == 401
    assert await _righe() == []


async def test_chiave_sconosciuta(reset_db: None) -> None:
    """Un dispositivo senza chiave (approvato prima della 081) o che non esiste."""
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    risposta = await _post(_ingestore(), _corpo(), firma=_firma(chiave, _corpo()))
    assert risposta.status_code == 401
    altro = "pluvio-matera-99"
    risposta = await _post(
        _ingestore(),
        _corpo(),
        firma=_firma(chiave, _corpo(), device_id=altro),
        url=f"/sensori/v2/{altro}/obs",
    )
    assert risposta.status_code == 401
    assert await _righe() == []


async def test_doppione_troppo_grande_e_id_non_valido(reset_db: None) -> None:
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    await _registra(chiave)
    ing = _ingestore()
    assert (await _post(ing, _corpo(), firma=_firma(chiave, _corpo()))).status_code == 200
    doppione = await _post(ing, _corpo(), firma=_firma(chiave, _corpo()))
    assert doppione.status_code == 409
    assert doppione.json() == {"esito": "sequenza"}

    grande = json.dumps([{"n": "x" * 3000}]).encode()
    assert (await _post(ing, grande, firma=_firma(chiave, grande))).status_code == 413
    assert (
        await _post(ing, _corpo(2), firma="", url="/sensori/v2/Non_Valido/obs")
    ).status_code == 404
    assert len(await _righe()) == 1


async def test_frequenza_come_mqtt(reset_db: None) -> None:
    """Il limite al minuto è quello dell'ingestore: HTTP e MQTT lo condividono."""
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    await _registra(chiave)
    ing = _ingestore(max_messaggi_al_minuto=1)
    assert await ing.gestisci(topic=TOPIC, payload=_corpo(1)) is Esito.SALVATO
    risposta = await _post(ing, _corpo(2), firma=_firma(chiave, _corpo(2)))
    assert risposta.status_code == 429


async def test_un_messaggio_rimandato_non_consuma_la_quota(reset_db: None) -> None:
    """Un POST intercettato e rimandato non deve mettere in quarantena il
    dispositivo vero: entra una volta, e le copie non contano per la frequenza."""
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    await _registra(chiave)
    ing = _ingestore(max_messaggi_al_minuto=2, scarti_per_quarantena=2)
    firma = _firma(chiave, _corpo(1))
    assert (await _post(ing, _corpo(1), firma=firma)).status_code == 200
    for _ in range(5):
        assert (await _post(ing, _corpo(1), firma=firma)).status_code == 409
    assert (await _post(ing, _corpo(2), firma=_firma(chiave, _corpo(2)))).status_code == 200
    dispositivo = await sensor_devices_repo.get_device(ID)
    assert dispositivo is not None and dispositivo.status != "quarantined"


async def test_l_arretrato_del_broker_non_vale_per_http(reset_db: None) -> None:
    """L'esenzione dopo una riconnessione (#273) è per ciò che consegna il broker."""
    await _cella_e_dispositivo()
    chiave = ed25519.Ed25519PrivateKey.generate()
    await _registra(chiave)
    ing = _ingestore(max_messaggi_al_minuto=1)
    ing._connesso_alle = ADESSO - timedelta(minutes=1)
    # Misura dopo la connessione: conta per la frequenza.
    adesso = _msg(1, ("rainfall", "mm", 1.0, ADESSO))
    assert await ing.gestisci(topic=TOPIC, payload=adesso) is Esito.SALVATO
    # Misura di prima della connessione: dal broker passerebbe, via HTTP no.
    risposta = await _post(ing, _corpo(2), firma=_firma(chiave, _corpo(2)))
    assert risposta.status_code == 429
