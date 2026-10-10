"""I contributi degli esperti: endpoint, difese, mail (repo e SMTP finti)."""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import contributi as contributi_ep
from limen.config.settings import ContributiSettings, EmailChannelSettings, Settings
from limen.core import contributi
from limen.data.repos import contributi_repo
from limen.notifications import email as email_mod

_STATO: dict[str, Any] = {
    "aoi_id": "it-basilicata",
    "lon": 16.10512,
    "lat": 40.10533,
    "pericoli": [
        {
            "hazard": "landslide",
            "score": 0.31,
            "classe": "Low",
            "calcolato": "2026-10-10T08:00:00+00:00",
            "fattori": {"S": 0.62, "M": 0.12, "note": "testo", "measured": True},
        }
    ],
}

_MODULO: dict[str, Any] = {
    "cell_id": "it-basilicata|12|34",
    "hazard": "landslide",
    "tipo": "frana_non_censita",
    "testo": "Sotto la strada provinciale c'è un corpo di frana attivo dal 2021.",
    "fonte_url": "https://www.example.org/relazione.pdf",
    "nome": "Maria Rossi",
    "email": "maria@example.org",
    "affiliazione": "Dipartimento di Scienze della Terra",
    "linkedin_url": "https://www.linkedin.com/in/maria-rossi",
    "consenso": True,
    "compilato_in_ms": 30_000,
}


class _Deps:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


class _Posta:
    def __init__(self, *, parte: bool = True, errore: Exception | None = None) -> None:
        self.parte = parte
        self.errore = errore
        self.mail: list[dict[str, Any]] = []

    async def invia(self, settings: Any, **kw: Any) -> bool:
        self.mail.append(kw)
        if self.errore is not None:
            raise self.errore
        return self.parte


def _client(
    monkeypatch: pytest.MonkeyPatch,
    posta: _Posta,
    *,
    cella: bool = True,
    destinatari: list[str] | None = None,
    **limiti: Any,
) -> TestClient:
    async def _stato(cell_id: str) -> dict[str, Any] | None:
        return _STATO if cella else None

    monkeypatch.setattr(contributi_repo, "stato_cella", _stato)
    monkeypatch.setattr(contributi_ep, "invia_testo", posta.invia)
    # Un limitatore nuovo per test: quello di modulo ricorderebbe gli invii
    # dei test precedenti.
    monkeypatch.setattr(contributi, "LIMITATORE", contributi.Limitatore())
    app = FastAPI()
    app.state.deps = _Deps(
        Settings(
            contributi=ContributiSettings(
                destinatari=["cura@example.org"] if destinatari is None else destinatari,
                **limiti,
            )
        )
    )
    app.include_router(contributi_ep.router)
    return TestClient(app)


def test_manda_la_mail_con_reply_to_e_non_salva(monkeypatch: pytest.MonkeyPatch) -> None:
    posta = _Posta()
    r = _client(monkeypatch, posta).post("/api/contributi", json=_MODULO)
    assert r.status_code == 201
    assert r.json() == {"ricevuto": True}
    assert posta.mail[0]["destinatari"] == ["cura@example.org"]
    assert posta.mail[0]["rispondi_a"] == "maria@example.org"
    assert "S = 0.62" in posta.mail[0]["testo"]


@pytest.mark.parametrize(
    "posta",
    [_Posta(parte=False), _Posta(errore=RuntimeError("SMTP rotto"))],
    ids=["non-parte", "eccezione"],
)
def test_se_la_mail_non_parte_lo_dice(monkeypatch: pytest.MonkeyPatch, posta: _Posta) -> None:
    client = _client(monkeypatch, posta, max_per_ip_ora=1)
    assert client.post("/api/contributi", json=_MODULO).status_code == 503
    # Il posto torna libero: l'invio fallito non consuma il limite.
    posta.parte, posta.errore = True, None
    assert client.post("/api/contributi", json=_MODULO).status_code == 201


def test_senza_destinatari_non_parte(monkeypatch: pytest.MonkeyPatch) -> None:
    posta = _Posta()
    r = _client(monkeypatch, posta, destinatari=[]).post("/api/contributi", json=_MODULO)
    assert r.status_code == 503
    assert posta.mail == []


@pytest.mark.parametrize(
    "modifica",
    [{"sito_web": "http://spam.example"}, {"compilato_in_ms": 1200}],
    ids=["campo-esca", "troppo-veloce"],
)
def test_un_programma_riceve_un_201_e_non_parte_niente(
    monkeypatch: pytest.MonkeyPatch, modifica: dict[str, Any]
) -> None:
    posta = _Posta()
    r = _client(monkeypatch, posta).post("/api/contributi", json={**_MODULO, **modifica})
    assert r.status_code == 201
    assert posta.mail == []


def test_limite_per_indirizzo(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _Posta(), max_per_ip_ora=2)
    codici = [client.post("/api/contributi", json=_MODULO).status_code for _ in range(3)]
    assert codici == [201, 201, 429]
    # Un altro indirizzo, dichiarato da nginx in X-Real-IP, ha i suoi posti.
    altro = client.post("/api/contributi", json=_MODULO, headers={"X-Real-IP": "203.0.113.9"})
    assert altro.status_code == 201


def test_limite_complessivo(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, _Posta(), max_per_ip_ora=5, max_totali_ora=2)
    codici = [
        client.post(
            "/api/contributi", json=_MODULO, headers={"X-Real-IP": f"203.0.113.{i}"}
        ).status_code
        for i in range(3)
    ]
    assert codici == [201, 201, 429]


def test_cella_che_non_esiste_404(monkeypatch: pytest.MonkeyPatch) -> None:
    posta = _Posta()
    r = _client(monkeypatch, posta, cella=False).post("/api/contributi", json=_MODULO)
    assert r.status_code == 404
    assert posta.mail == []


def test_basta_il_profilo_linkedin_al_posto_del_nome(monkeypatch: pytest.MonkeyPatch) -> None:
    posta = _Posta()
    modulo = {k: v for k, v in _MODULO.items() if k != "nome"}
    r = _client(monkeypatch, posta).post("/api/contributi", json=modulo)
    assert r.status_code == 201
    assert "Nome: non indicato" in posta.mail[0]["testo"]
    assert "LinkedIn: https://www.linkedin.com/in/maria-rossi" in posta.mail[0]["testo"]


@pytest.mark.parametrize(
    "modifica",
    [
        {"consenso": False},
        {"testo": "troppo corto"},
        {"email": "maria@example.org\nBcc: tutti@example.org"},
        {"fonte_url": "javascript:alert(1)"},
        {"linkedin_url": "ftp://example.org/profilo"},
        {"nome": None, "linkedin_url": None},
        {"campo_in_piu": "x"},
    ],
    ids=[
        "consenso",
        "testo-corto",
        "email-a-capo",
        "url-javascript",
        "url-ftp",
        "ne-nome-ne-linkedin",
        "campo-extra",
    ],
)
def test_modulo_non_valido_422(monkeypatch: pytest.MonkeyPatch, modifica: dict[str, Any]) -> None:
    posta = _Posta()
    r = _client(monkeypatch, posta).post("/api/contributi", json={**_MODULO, **modifica})
    assert r.status_code == 422
    assert posta.mail == []


def test_la_mail_porta_tutto_quello_che_serve() -> None:
    dati = contributi.ContributoIn.model_validate(_MODULO)
    oggetto, testo = contributi.componi_mail(
        dati, _STATO, map_base_url="https://limen.example.org/"
    )
    assert oggetto == "[Limen] Contributo esperto · Frana non censita · it-basilicata|12|34"
    assert "Contributo — Frana non censita" in testo
    assert "Fonte: https://www.example.org/relazione.pdf" in testo
    assert "Nome: Maria Rossi" in testo
    assert "Email: maria@example.org" in testo
    assert "Dipartimento o ente: Dipartimento di Scienze della Terra" in testo
    assert "Coordinate: 40.10533, 16.10512" in testo
    assert (
        "Mappa: https://limen.example.org/?aoi=it-basilicata&cell=it-basilicata%7C12%7C34" in testo
    )
    assert "S = 0.62" in testo
    # Solo i fattori numerici: un testo o un booleano non sono un numero da leggere.
    assert "note =" not in testo
    assert "measured =" not in testo


@pytest.mark.asyncio
async def test_il_limitatore_e_atomico() -> None:
    """Venti invii insieme dallo stesso indirizzo: ne passano quanti il limite."""
    lim = contributi.Limitatore()
    esiti = await asyncio.gather(
        *(lim.prenota("203.0.113.7", max_per_ip=3, max_totali=30) for _ in range(20))
    )
    assert sum(e is not None for e in esiti) == 3


@pytest.mark.asyncio
async def test_invia_testo_mette_il_reply_to(monkeypatch: pytest.MonkeyPatch) -> None:
    spediti: list[EmailMessage] = []

    async def _send(msg: EmailMessage, **kw: Any) -> None:
        spediti.append(msg)

    monkeypatch.setattr(email_mod.aiosmtplib, "send", _send)
    cfg = EmailChannelSettings(smtp_host="smtp.example.org", from_address="limen@example.org")
    ok = await email_mod.invia_testo(
        cfg,
        destinatari=["cura@example.org"],
        oggetto="Prova",
        testo="Corpo",
        rispondi_a="maria@example.org",
    )
    assert ok is True
    assert spediti[0]["Reply-To"] == "maria@example.org"
    assert spediti[0]["To"] == "cura@example.org"
    assert spediti[0]["From"] == "limen@example.org"


@pytest.mark.asyncio
async def test_invia_testo_senza_smtp_non_parte() -> None:
    ok = await email_mod.invia_testo(
        EmailChannelSettings(),
        destinatari=["cura@example.org"],
        oggetto="Prova",
        testo="Corpo",
    )
    assert ok is False
