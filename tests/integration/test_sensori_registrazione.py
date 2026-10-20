"""Registrazione dei sensori (#253) contro PostGIS vero.

Il flusso del criterio di accettazione: modulo → approva → certificato →
prima osservazione accettata → revoca → osservazione rifiutata. La CA e la
posta sono finte: firmare e revocare li prova ``make sensori-check`` sul
broker vero, qui conta cosa cambia nel registro.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

import asyncpg
import httpx
import pytest
from shapely.geometry import Polygon

from limen.cli import sensore
from limen.config.settings import (
    IotCittadiniSettings,
    IotSettings,
    SensoriRegistrazioneSettings,
    get_settings,
)
from limen.core import contributi
from limen.core import sensori_registrazione as reg
from limen.data.db import acquire
from limen.data.repos import aoi_repo, grid_repo, sensor_devices_repo
from limen.integrations.iot.ingestore_v2 import Esito, IngestoreV2
from limen.integrations.iot.ingresso_http import applicazione
from tests.integration.test_iot_ttn import UPLINK
from tests.unit.test_sensori_registrazione import csr_pem, modulo

pytestmark = pytest.mark.integration

ID = "pluvio-matera-01"
MAIL = "maker@example.org"
ADESSO = datetime(2026, 6, 1, 11, 30, tzinfo=UTC)


class _CaFinta(sensore.CaSensori):
    def __init__(self) -> None:
        super().__init__("/non/esiste")
        self.firmate: list[str] = []
        self.revocati: list[str] = []

    async def firma(self, csr: str, *, giorni: int) -> str:
        self.firmate.append(csr)
        return f"-----BEGIN CERTIFICATE-----\n{len(self.firmate)}\n-----END CERTIFICATE-----\n"

    async def revoca(self, device_id: str) -> None:
        self.revocati.append(device_id)

    async def certificato_ca(self) -> str:
        return "-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----\n"


class _Posta:
    def __init__(self, *, parte: bool = True) -> None:
        self.parte = parte
        self.mail: list[dict[str, Any]] = []

    async def invia(self, *args: Any, **kw: Any) -> bool:
        self.mail.append(kw)
        return self.parte


@pytest.fixture
async def cella(reset_db: None) -> str:
    await aoi_repo.upsert_aoi(
        id="aoi-reg",
        name="reg",
        kind="test",
        geom=Polygon([(16.55, 40.62), (16.65, 40.62), (16.65, 40.70), (16.55, 40.70)]),
        metadata={},
    )
    await grid_repo.generate_and_store_grid("aoi-reg")
    async with acquire() as conn:
        cell_id: str = await conn.fetchval(
            """
            SELECT id FROM grid_cells
             WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint(16.6, 40.66), 4326))
            """
        )
    return cell_id


def _settings(**registrazione: Any) -> SensoriRegistrazioneSettings:
    return SensoriRegistrazioneSettings(aperta=True, **registrazione)


async def _ricevi(
    posta: _Posta, *, ip: str = "203.0.113.7", settings: Any = None, **modifiche: Any
) -> reg.Esito:
    return await reg.ricevi(
        reg.RichiestaSensoreIn.model_validate(modulo(**modifiche)),
        ip=ip,
        settings=settings or _settings(),
        destinatari=["cura@example.org"],
        invia=posta.invia,
        limitatore=contributi.Limitatore(),
    )


async def _richiesta_id(device_id: str = ID) -> int:
    async with acquire() as conn:
        rid: int = await conn.fetchval(
            "SELECT id FROM sensori_richieste WHERE device_id = $1", device_id
        )
    return rid


def _obs(seq: int) -> bytes:
    return json.dumps(
        [
            {"bn": f"{ID}/", "n": "rainfall", "u": "mm", "v": 1.5, "t": int(ADESSO.timestamp())},
            {"n": "seq", "v": seq},
        ]
    ).encode()


async def test_richiesta_approva_osserva_revoca(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    posta = _Posta()
    assert isinstance(await _ricevi(posta), reg.Ricevuta)
    [avviso] = posta.mail
    assert avviso["rispondi_a"] == MAIL
    rid = await _richiesta_id()
    assert f"limen sensore approva {rid}" in avviso["testo"]
    assert [a[1] for a in avviso["allegati"]] == ["image/jpeg"]
    # La richiesta non crea il dispositivo.
    assert await sensor_devices_repo.get_device(ID) is None

    ca = _CaFinta()
    posta_cli = _Posta()
    monkeypatch.setattr(sensore, "invia_testo", posta_cli.invia)
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    dispositivo = await sensor_devices_repo.get_device(ID)
    assert dispositivo is not None
    assert (dispositivo.livello, dispositivo.status, dispositivo.cell_id) == (0, "offline", cella)
    # La chiave della CSR, per l'ingresso HTTP firmato (#265).
    assert await sensor_devices_repo.chiave_pubblica(ID) is not None
    [consegna] = posta_cli.mail
    assert consegna["destinatari"] == [MAIL]
    assert [a[0] for a in consegna["allegati"]] == [f"{ID}.crt", "ca.crt"]

    ingestore = IngestoreV2(
        IotSettings(cittadini=IotCittadiniSettings(enabled=True)), adesso=lambda: ADESSO
    )
    assert await ingestore.gestisci(topic=f"limen/v2/{ID}/obs", payload=_obs(1)) is Esito.SALVATO

    assert await sensore.revoca(ID, ca=ca) == 0
    assert ca.revocati == [ID]
    assert await ingestore.gestisci(topic=f"limen/v2/{ID}/obs", payload=_obs(2)) is Esito.QUARANTENA
    # Rilanciare `approva` non rimanda un certificato revocato.
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 1
    assert len(posta_cli.mail) == 1
    # Un LWT «online» non toglie la revoca.
    await ingestore.gestisci(topic=f"limen/v2/{ID}/status", payload=b"online")
    dispositivo = await sensor_devices_repo.get_device(ID)
    assert dispositivo is not None and dispositivo.status == "quarantined"


async def test_approva_due_volte_rimanda_lo_stesso_certificato(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ricevi(_Posta())
    rid = await _richiesta_id()
    ca = _CaFinta()
    posta = _Posta()
    monkeypatch.setattr(sensore, "invia_testo", posta.invia)
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    assert len(ca.firmate) == 1
    assert posta.mail[0]["allegati"][0][2] == posta.mail[1]["allegati"][0][2]


async def test_rilanciare_approva_aggiunge_la_chiave_mancante(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un dispositivo approvato prima della 081 ottiene la chiave per l'HTTP (#265)."""
    await _ricevi(_Posta())
    rid = await _richiesta_id()
    ca = _CaFinta()
    monkeypatch.setattr(sensore, "invia_testo", _Posta().invia)
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    chiave = await sensor_devices_repo.chiave_pubblica(ID)
    async with acquire() as conn:
        await conn.execute("UPDATE sensor_devices SET chiave_pubblica = NULL WHERE id = $1", ID)
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    assert await sensor_devices_repo.chiave_pubblica(ID) == chiave


async def test_mail_non_partita_rimanda_alla_cli(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ricevi(_Posta())
    rid = await _richiesta_id()
    monkeypatch.setattr(sensore, "invia_testo", _Posta(parte=False).invia)
    assert await sensore.approva(rid, settings=get_settings(), ca=_CaFinta()) == 1
    # Il dispositivo esiste: rilanciare `approva` rimanda solo la mail.
    assert await sensor_devices_repo.get_device(ID) is not None


async def test_id_gia_usato_da_un_altro_non_si_approva(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _ricevi(_Posta())
    rid = await _richiesta_id()
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_devices (id, device_type, location, livello)
            VALUES ($1, 'rain_gauge', ST_SetSRID(ST_MakePoint(16.6, 40.66), 4326), 2)
            """,
            ID,
        )
    monkeypatch.setattr(sensore, "invia_testo", _Posta().invia)
    ca = _CaFinta()
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 1
    assert ca.firmate == []


async def test_respinta_non_si_approva(cella: str) -> None:
    await _ricevi(_Posta())
    rid = await _richiesta_id()
    assert await sensore.respingi(rid) == 0
    assert await sensore.respingi(rid) == 0
    assert await sensore.approva(rid, settings=get_settings(), ca=_CaFinta()) == 1


async def test_se_la_mail_non_parte_non_resta_niente(cella: str) -> None:
    assert isinstance(await _ricevi(_Posta(parte=False)), reg.NonPartita)
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM sensori_richieste") == 0
        assert await conn.fetchval("SELECT count(*) FROM sensori_registranti") == 0


async def test_quota_per_registrante(cella: str) -> None:
    settings = _settings(max_dispositivi_per_registrante=1)
    assert isinstance(await _ricevi(_Posta(), settings=settings), reg.Ricevuta)
    esito = await _ricevi(
        _Posta(), settings=settings, csr=csr_pem("pluvio-matera-02"), email="MAKER@example.org"
    )
    assert isinstance(esito, reg.NonValida) and "massimo" in esito.motivo


async def test_id_in_uso_e_posizione_fuori(cella: str) -> None:
    await _ricevi(_Posta())
    esito = await _ricevi(_Posta(), email="altro@example.org")
    assert isinstance(esito, reg.NonValida) and "già in uso" in esito.motivo
    esito = await _ricevi(_Posta(), csr=csr_pem("pluvio-fuori"), lon=9.19, lat=45.46)
    assert isinstance(esito, reg.NonValida) and "fuori" in esito.motivo


async def test_cancella_registrante(cella: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GDPR: la mail sparisce, i dispositivi restano in quarantena e revocati."""
    await _ricevi(_Posta())
    await _ricevi(_Posta(), csr=csr_pem("pluvio-matera-02"))
    monkeypatch.setattr(sensore, "invia_testo", _Posta().invia)
    ca = _CaFinta()
    assert await sensore.approva(await _richiesta_id(), settings=get_settings(), ca=ca) == 0

    assert await sensore.cancella_registrante("Maker@example.org", ca=ca) == 0
    assert await sensore.cancella_registrante(MAIL, ca=ca) == 0
    assert ca.revocati == [ID]
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM sensori_registranti") == 0
        assert await conn.fetchval("SELECT count(*) FROM sensori_richieste") == 0
        row = await conn.fetchrow(
            """
            SELECT d.status, d.registrante_id, d.metadata ? 'richiesta' AS rimando,
                   ST_Equals(d.location, g.centroid) AS sul_centroide
              FROM sensor_devices d JOIN grid_cells g ON g.id = d.cell_id
             WHERE d.id = $1
            """,
            ID,
        )
    assert dict(row) == {
        "status": "quarantined",
        "registrante_id": None,
        "rimando": False,
        "sul_centroide": True,
    }


async def test_quarantena_per_registrante(cella: str, monkeypatch: pytest.MonkeyPatch) -> None:
    await _ricevi(_Posta())
    monkeypatch.setattr(sensore, "invia_testo", _Posta().invia)
    await sensore.approva(await _richiesta_id(), settings=get_settings(), ca=_CaFinta())
    assert await sensore.quarantena(None, registrante=MAIL) == 0
    dispositivo = await sensor_devices_repo.get_device(ID)
    assert dispositivo is not None and dispositivo.status == "quarantined"
    assert await sensore.quarantena(None, registrante="nessuno@example.org") == 1


async def test_cli_richieste(cella: str) -> None:
    await _ricevi(_Posta())
    args = argparse.Namespace(sensore_command="richieste")
    assert await sensore.run(args, ca=_CaFinta()) == 0


async def test_stesso_id_in_parallelo_un_solo_invio(cella: str) -> None:
    csr = csr_pem("pluvio-doppio")
    esiti = await asyncio.gather(
        *(_ricevi(_Posta(), csr=csr, email=f"m{i}@example.org", ip=f"ip{i}") for i in range(3))
    )
    assert sum(isinstance(e, reg.Ricevuta) for e in esiti) == 1
    assert all(isinstance(e, reg.Ricevuta | reg.NonValida) for e in esiti)


async def test_ricevi_tiene_la_quota_contro_invii_paralleli(cella: str) -> None:
    settings = _settings(max_dispositivi_per_registrante=1)
    esiti = await asyncio.gather(
        *(
            _ricevi(_Posta(), settings=settings, csr=csr_pem(f"pluvio-par-{i:02d}"), ip=f"ip{i}")
            for i in range(4)
        )
    )
    assert sum(isinstance(e, reg.Ricevuta) for e in esiti) == 1


LORA: dict[str, Any] = {
    "modo": "lorawan",
    "csr": None,
    "device_id": ID,
    # Come lo stampa la console TTN, con i separatori.
    "dev_eui": "70-B3-D5-7E-D0-01-23-45",
    "ttn_applicazione": "pluviometri-matera",
}


def _segreto_nella_mail(testo: str) -> str | None:
    trovato = re.search(r"Authorization: Bearer (\S+)", testo)
    return None if trovato is None else trovato.group(1)


async def _uplink(ingestore: IngestoreV2, segreto: str) -> httpx.Response:
    app = applicazione(ingestore.gestisci, ingestore._c, adesso=lambda: ADESSO)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://sensori"
    ) as client:
        return await client.post(
            "/sensori/v2/ttn",
            content=json.dumps(UPLINK).encode(),
            headers={"Authorization": f"Bearer {segreto}"},
        )


async def test_lorawan_richiesta_approva_webhook(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#266: modulo LoRaWAN → approva → segreto per mail → l'uplink TTN entra."""
    posta = _Posta()
    assert isinstance(await _ricevi(posta, **LORA), reg.Ricevuta)
    [avviso] = posta.mail
    assert "DevEUI: 70B3D57ED0012345" in avviso["testo"]
    assert "Applicazione TTN: pluviometri-matera" in avviso["testo"]
    rid = await _richiesta_id()

    ca = _CaFinta()
    posta_cli = _Posta()
    monkeypatch.setattr(sensore, "invia_testo", posta_cli.invia)
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    assert ca.firmate == []
    [consegna] = posta_cli.mail
    segreto = _segreto_nella_mail(consegna["testo"])
    assert segreto is not None and len(segreto) >= 40
    async with acquire() as conn:
        # Nel database solo l'impronta.
        assert await conn.fetchval("SELECT segreto_sha256 FROM sensori_ttn") == (
            hashlib.sha256(segreto.encode()).digest()
        )
    dispositivo = await sensor_devices_repo.get_device(ID)
    assert dispositivo is not None and (dispositivo.livello, dispositivo.status) == (0, "offline")
    assert await sensor_devices_repo.per_dev_eui("70B3D57ED0012345") == (ID, "pluviometri-matera")

    ingestore = IngestoreV2(
        IotSettings(cittadini=IotCittadiniSettings(enabled=True)), adesso=lambda: ADESSO
    )
    risposta = await _uplink(ingestore, segreto)
    assert (risposta.status_code, risposta.json()) == (200, {"esito": "salvato"})

    # Rilanciare `approva` rimanda la mail, ma un segreto non si rimanda.
    assert await sensore.approva(rid, settings=get_settings(), ca=ca) == 0
    assert _segreto_nella_mail(posta_cli.mail[1]["testo"]) is None

    # Un segreto perso si sostituisce: il vecchio smette di valere.
    assert await sensore.ttn_segreto("pluviometri-matera", settings=get_settings()) == 0
    nuovo = _segreto_nella_mail(posta_cli.mail[2]["testo"])
    assert nuovo is not None and nuovo != segreto
    assert posta_cli.mail[2]["destinatari"] == [MAIL]
    assert (await _uplink(ingestore, segreto)).status_code == 401
    assert (await _uplink(ingestore, nuovo)).status_code == 202  # stessa seq: doppione
    assert await sensore.ttn_segreto("non-esiste", settings=get_settings()) == 1


async def test_lorawan_seconda_applicazione_e_applicazione_altrui(
    cella: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    posta_cli = _Posta()
    monkeypatch.setattr(sensore, "invia_testo", posta_cli.invia)
    await _ricevi(_Posta(), **LORA)
    assert await sensore.approva(await _richiesta_id(), settings=get_settings(), ca=_CaFinta()) == 0

    # Un secondo dispositivo nella stessa applicazione: vale il segreto già dato.
    await _ricevi(
        _Posta(),
        ip="203.0.113.8",
        **{**LORA, "device_id": "pluvio-matera-02", "dev_eui": "70B3D57ED0012346"},
    )
    assert (
        await sensore.approva(
            await _richiesta_id("pluvio-matera-02"), settings=get_settings(), ca=_CaFinta()
        )
        == 0
    )
    assert _segreto_nella_mail(posta_cli.mail[1]["testo"]) is None

    # Un altro registrante non si prende un'applicazione che non è sua.
    await _ricevi(
        _Posta(),
        ip="203.0.113.9",
        email="altro@example.org",
        **{**LORA, "device_id": "pluvio-matera-03", "dev_eui": "70B3D57ED0012347"},
    )
    assert (
        await sensore.approva(
            await _richiesta_id("pluvio-matera-03"), settings=get_settings(), ca=_CaFinta()
        )
        == 1
    )
    assert await sensor_devices_repo.get_device("pluvio-matera-03") is None
    async with acquire() as conn:
        assert (
            await conn.fetchval(
                "SELECT stato FROM sensori_richieste WHERE device_id = 'pluvio-matera-03'"
            )
            == "in_attesa"
        )


async def test_lorawan_dev_eui_gia_registrato(cella: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensore, "invia_testo", _Posta().invia)
    assert isinstance(await _ricevi(_Posta(), **LORA), reg.Ricevuta)
    doppio = await _ricevi(_Posta(), ip="203.0.113.8", **{**LORA, "device_id": "pluvio-matera-02"})
    assert isinstance(doppio, reg.NonValida) and "DevEUI" in doppio.motivo
    assert await sensore.approva(await _richiesta_id(), settings=get_settings(), ca=_CaFinta()) == 0
    dopo = await _ricevi(_Posta(), ip="203.0.113.9", **{**LORA, "device_id": "pluvio-matera-04"})
    assert isinstance(dopo, reg.NonValida) and "DevEUI" in dopo.motivo


async def test_la_richiesta_con_un_solo_campo_lorawan_non_entra(cella: str) -> None:
    """Il CHECK della 082 non si fida del modulo: una regex su NULL vale NULL."""
    async with acquire() as conn:
        rid = await conn.fetchval(
            "INSERT INTO sensori_registranti (email) VALUES ('x@example.org') RETURNING id"
        )
        for dev_eui, app in [(None, "app-ok"), ("70B3D57ED0012345", None), ("0" * 16, "app-ok")]:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    "INSERT INTO sensori_richieste (registrante_id, device_id, device_type, lon, "
                    "lat, licenza, dev_eui, ttn_applicazione) "
                    "VALUES ($1, 'x-01', 'pluviometro', 16.6, 40.66, 'CC-BY-4.0', $2, $3)",
                    rid,
                    dev_eui,
                    app,
                )


async def test_cancella_registrante_lorawan(cella: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """GDPR (#266): via l'applicazione TTN e il suo segreto, il DevEUI torna libero."""
    posta_cli = _Posta()
    monkeypatch.setattr(sensore, "invia_testo", posta_cli.invia)
    await _ricevi(_Posta(), **LORA)
    assert await sensore.approva(await _richiesta_id(), settings=get_settings(), ca=_CaFinta()) == 0
    segreto = _segreto_nella_mail(posta_cli.mail[0]["testo"])
    assert segreto is not None

    assert await sensore.cancella_registrante(MAIL, ca=_CaFinta()) == 0
    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM sensori_ttn") == 0
        row = await conn.fetchrow(
            "SELECT status, dev_eui, ttn_applicazione FROM sensor_devices WHERE id = $1", ID
        )
    assert dict(row) == {"status": "quarantined", "dev_eui": None, "ttn_applicazione": None}
    ingestore = IngestoreV2(
        IotSettings(cittadini=IotCittadiniSettings(enabled=True)), adesso=lambda: ADESSO
    )
    assert (await _uplink(ingestore, segreto)).status_code == 401
    assert not await reg.repo.dev_eui_in_uso("70B3D57ED0012345")
