"""Registrazione dei sensori (#253): CSR, foto, endpoint e difese (repo e SMTP finti)."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.x509.oid import NameOID
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import sensori as sensori_ep
from limen.config.settings import (
    ContributiSettings,
    EmailChannelSettings,
    IotCittadiniSettings,
    IotSettings,
    SensoriRegistrazioneSettings,
    Settings,
)
from limen.core import contributi
from limen.core import sensori_registrazione as reg
from limen.notifications import email as email_mod


def csr_pem(cn: str = "pluvio-matera-01", *, chiave: Any = None, **altri: str) -> str:
    chiave = chiave or ec.generate_private_key(ec.SECP256R1())
    attributi = [x509.NameAttribute(NameOID.COMMON_NAME, cn)]
    attributi += [x509.NameAttribute(NameOID.COMMON_NAME, v) for v in altri.values()]
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name(attributi))
        # Ed25519 firma senza un hash a parte.
        .sign(chiave, None if isinstance(chiave, ed25519.Ed25519PrivateKey) else hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


_JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 100


def modulo(**modifiche: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "tipo": "pluviometro",
        "lon": 16.6,
        "lat": 40.66,
        "csr": csr_pem(),
        "email": "Maker@Example.org",
        "note": "Sul tetto del garage, a 3 m da terra.",
        "foto": base64.b64encode(_JPEG).decode(),
        "licenza": "CC-BY-4.0",
        "regole_sicurezza": True,
        "informativa": True,
        "compilato_in_ms": 60_000,
    }
    base.update(modifiche)
    return base


def test_csr_valida() -> None:
    chiave = ec.generate_private_key(ec.SECP256R1())
    csr = reg.leggi_csr(csr_pem(chiave=chiave))
    assert csr.device_id == "pluvio-matera-01"
    assert len(csr.impronta.split(":")) == 32
    assert csr.chiave == chiave.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def test_csr_ed25519_per_l_ingresso_http() -> None:
    """#265: un dispositivo che consegna solo via HTTP può avere una Ed25519."""
    chiave = ed25519.Ed25519PrivateKey.generate()
    csr = reg.leggi_csr(csr_pem("datalogger-01", chiave=chiave))
    assert csr.device_id == "datalogger-01"
    assert csr.chiave == chiave.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


@pytest.mark.parametrize(
    ("pem", "motivo"),
    [
        ("non è una csr" * 10, "PEM"),
        (csr_pem(chiave=ec.generate_private_key(ec.SECP384R1())), "P-256"),
        (csr_pem(chiave=rsa.generate_private_key(public_exponent=65537, key_size=2048)), "P-256"),
        (csr_pem("Pluvio_Matera"), "minuscole"),
        (csr_pem("limen-ingestore"), "riservato"),
        (csr_pem("pluvio-a\n"), "minuscole"),
        (csr_pem("pluvio-a", secondo="pluvio-b"), "un solo CN"),
    ],
)
def test_csr_non_valida(pem: str, motivo: str) -> None:
    with pytest.raises(reg.CsrNonValidaError, match=motivo):
        reg.leggi_csr(pem)


def test_csr_con_firma_alterata() -> None:
    """La firma prova che chi manda la CSR ha la chiave: una CSR copiata e
    modificata non passa."""
    der = x509.load_pem_x509_csr(csr_pem().encode()).public_bytes(serialization.Encoding.DER)
    alterata = der[:-4] + bytes(b ^ 0xFF for b in der[-4:])
    pem = x509.load_der_x509_csr(alterata).public_bytes(serialization.Encoding.PEM).decode()
    with pytest.raises(reg.CsrNonValidaError, match="firma"):
        reg.leggi_csr(pem)


def test_foto() -> None:
    assert reg._foto(base64.b64encode(_JPEG).decode(), max_kb=1)[1] == "image/jpeg"
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 10
    assert reg._foto(base64.b64encode(png).decode(), max_kb=1)[0] == "installazione.png"
    with pytest.raises(ValueError, match="JPEG o PNG"):
        reg._foto(base64.b64encode(b"GIF89a....").decode(), max_kb=1)
    with pytest.raises(ValueError, match="supera"):
        reg._foto(base64.b64encode(_JPEG + b"\0" * 2048).decode(), max_kb=1)
    with pytest.raises(ValueError, match="base64"):
        reg._foto("%%%", max_kb=1)


class _Deps:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


class _Posta:
    def __init__(self) -> None:
        self.mail: list[dict[str, Any]] = []

    async def invia(self, settings: Any, **kw: Any) -> bool:
        self.mail.append(kw)
        return True


def _client(monkeypatch: pytest.MonkeyPatch, posta: _Posta, **registrazione: Any) -> TestClient:
    monkeypatch.setattr(sensori_ep, "invia_testo", posta.invia)
    monkeypatch.setattr(reg, "LIMITATORE", contributi.Limitatore())
    app = FastAPI()
    app.state.deps = _Deps(
        Settings(
            contributi=ContributiSettings(destinatari=["cura@example.org"]),
            iot=IotSettings(
                cittadini=IotCittadiniSettings(
                    registrazione=SensoriRegistrazioneSettings(**registrazione)
                )
            ),
        )
    )
    app.include_router(sensori_ep.router)
    return TestClient(app)


def test_chiusa_per_default(monkeypatch: pytest.MonkeyPatch) -> None:
    posta = _Posta()
    client = _client(monkeypatch, posta)
    assert client.get("/api/sensori/registrazione").json() == {"aperta": False}
    r = client.post("/api/sensori/registrazione", json=modulo())
    assert r.status_code == 503
    assert "non sono ancora aperte" in r.json()["detail"]
    assert posta.mail == []


@pytest.mark.parametrize(
    "modifiche", [{"sito_web": "https://spam.example"}, {"compilato_in_ms": 3_000}]
)
def test_un_programma_riceve_un_201_e_non_parte_niente(
    monkeypatch: pytest.MonkeyPatch, modifiche: dict[str, Any]
) -> None:
    posta = _Posta()
    client = _client(monkeypatch, posta, aperta=True)
    r = client.post("/api/sensori/registrazione", json=modulo(**modifiche))
    assert r.status_code == 201
    assert posta.mail == []


@pytest.mark.parametrize(
    "modifiche",
    [
        {"licenza": "proprietaria"},
        {"regole_sicurezza": False},
        {"informativa": False},
        {"tipo": "inclinometro"},
        {"email": "non-una-mail"},
        {"email": "a@b.it\r\nBcc: tutti@example.org"},
        {"lat": 91},
        {"chiave_privata": "-----BEGIN EC PRIVATE KEY-----"},
    ],
)
def test_modulo_non_valido_422(monkeypatch: pytest.MonkeyPatch, modifiche: dict[str, Any]) -> None:
    client = _client(monkeypatch, _Posta(), aperta=True)
    assert client.post("/api/sensori/registrazione", json=modulo(**modifiche)).status_code == 422


def test_csr_non_valida_dice_perche(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _Posta(), aperta=True)
    r = client.post("/api/sensori/registrazione", json=modulo(csr=csr_pem("limen-salute")))
    assert r.status_code == 422
    assert "riservato" in r.json()["detail"]


def test_email_in_minuscolo() -> None:
    assert reg.RichiestaSensoreIn.model_validate(modulo()).email == "maker@example.org"


async def test_invia_testo_con_allegati(monkeypatch: pytest.MonkeyPatch) -> None:
    spedite: list[EmailMessage] = []

    async def _spedisci(settings: Any, msg: EmailMessage) -> bool:
        spedite.append(msg)
        return True

    monkeypatch.setattr(email_mod, "_spedisci", _spedisci)
    assert await email_mod.invia_testo(
        EmailChannelSettings(smtp_host="smtp.example.org", from_address="limen@example.org"),
        destinatari=["maker@example.org"],
        oggetto="cert",
        testo="in allegato",
        allegati=[("dev.crt", "application/x-pem-file", b"-----BEGIN CERTIFICATE-----")],
    )
    [allegato] = list(spedite[0].iter_attachments())
    assert allegato.get_filename() == "dev.crt"
    assert allegato.get_content_type() == "application/x-pem-file"
