"""L'API dell'installazione guidata (#403, #404): token e stato.

Il token è l'unica cosa fra una pagina pubblica e un download da 22 GB: un
endpoint che lo salta, o un server senza token che lascia passare, sono
proprio gli errori che questi test esistono per fermare.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from limen.api.dependencies import HEADER_TOKEN_INSTALLAZIONE
from limen.api.endpoints import installazione as ep
from limen.config.catalogo_dati import carica_catalogo
from limen.config.settings import InstallazioneSettings, Settings
from limen.core.installazione import mancanti
from limen.core.models.hazard import HazardType
from limen.data.repos.copertura_repo import Copertura
from limen.data.repos.dati_download_repo import StatoDownload

_TOKEN = "a" * 48


class _Deps:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


class _Coda:
    def __init__(self) -> None:
        self.accodate: list[str] = []

    async def accoda(self, voci: list[str], *, byte_totali: dict[str, int]) -> list[str]:
        self.accodate.extend(voci)
        return [v for v in voci if v != "dtm"]  # dtm è già in corso

    async def elenco(self) -> list[StatoDownload]:
        adesso = datetime(2026, 11, 4, tzinfo=UTC)
        return [
            StatoDownload(
                voce="dtm",
                stato="in_corso",
                byte_fatti=5_000_000_000,
                byte_totali=22_100_000_000,
                richiesto_il=adesso,
                avviato_il=adesso,
                aggiornato_il=adesso,
                finito_il=None,
                errore=None,
                tentativi=1,
            )
        ]


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    token: str | None = _TOKEN,
    copertura: dict[str, int] | None = None,
    celle: int = 312_550,
    per_regione: dict[str, dict[str, int]] | None = None,
) -> tuple[TestClient, _Coda]:
    coda = _Coda()
    monkeypatch.setattr(ep.coda, "accoda", coda.accoda)
    monkeypatch.setattr(ep.coda, "elenco", coda.elenco)

    conte = copertura or {}
    catalogo = carica_catalogo()
    per_cella = {v.id for v in catalogo.voci if v.misura.colonna is not None}
    # Due regioni con la stessa copertura, salvo `per_regione` esplicito.
    regioni = (
        per_regione
        if per_regione is not None
        else {
            "it-puglia": {k: n for k, n in conte.items() if k in per_cella},
            "it-basilicata": {k: n for k, n in conte.items() if k in per_cella},
        }
    )

    async def leggi(_: Any) -> Copertura:
        return Copertura(
            celle_totali=celle,
            regioni=len(regioni),
            totali=conte,
            per_regione=regioni if celle else {},
        )

    monkeypatch.setattr(ep.copertura_repo, "leggi", leggi)
    app = FastAPI()
    app.state.deps = _Deps(
        Settings(
            installazione=InstallazioneSettings(token=None if token is None else SecretStr(token))
        )
    )
    app.include_router(ep.router)
    return TestClient(app), coda


def _post(client: TestClient, token: str | None, voci: list[str]) -> Any:
    intestazioni = {} if token is None else {HEADER_TOKEN_INSTALLAZIONE: token}
    return client.post("/api/installazione/download", json={"voci": voci}, headers=intestazioni)


def test_senza_token_nell_header_non_si_scarica_niente(monkeypatch: pytest.MonkeyPatch) -> None:
    client, coda = _client(monkeypatch)
    assert _post(client, None, ["iffi"]).status_code == 401
    assert _post(client, "sbagliato", ["iffi"]).status_code == 401
    assert coda.accodate == []


def test_un_server_senza_token_tiene_chiuse_le_azioni(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail-closed: un token non configurato non è un token qualsiasi."""
    for vuoto in (None, "   "):
        client, coda = _client(monkeypatch, token=vuoto)
        risposta = _post(client, "", ["iffi"])
        assert risposta.status_code == 403
        assert "INSTALLAZIONE__TOKEN" in risposta.json()["detail"]
        assert coda.accodate == []


def test_con_il_token_si_accoda_e_si_dice_cosa_era_gia_in_corso(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, coda = _client(monkeypatch)
    risposta = _post(client, _TOKEN, ["iffi", "dtm"])
    assert risposta.status_code == 202
    assert risposta.json() == {"accodate": ["iffi"], "gia_in_corso": ["dtm"]}
    assert coda.accodate == ["iffi", "dtm"]


@pytest.mark.parametrize(("voce", "frammento"), [("meteo", "sconosciuta"), ("wui", "calcola")])
def test_voci_sconosciute_o_derivate_sono_rifiutate(
    monkeypatch: pytest.MonkeyPatch, voce: str, frammento: str
) -> None:
    client, coda = _client(monkeypatch)
    risposta = _post(client, _TOKEN, [voce])
    assert risposta.status_code == 422
    assert frammento in risposta.json()["detail"]
    assert coda.accodate == []


def test_lo_stato_e_pubblico_e_dice_cosa_manca(monkeypatch: pytest.MonkeyPatch) -> None:
    catalogo = carica_catalogo()
    tutto = {v.id: 1000 for v in catalogo.voci}
    client, _ = _client(monkeypatch, copertura=tutto | {"idraulica": 0})

    corpo = client.get("/api/installazione/stato").json()

    pericoli = {p["pericolo"]: p for p in corpo["pericoli"]}
    assert pericoli["flood"] == {"pericolo": "flood", "pronto": False, "mancano": ["idraulica"]}
    assert pericoli["landslide"]["pronto"]
    voci = {v["id"]: v for v in corpo["voci"]}
    assert voci["dtm"]["download"]["stato"] == "in_corso"
    assert voci["dtm"]["licenza"] == "CC-BY 4.0"
    assert voci["iffi"]["download"] is None
    assert corpo["azioni_abilitate"] is True


def test_senza_celle_nessun_pericolo_e_pronto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un database mai seminato non ha niente da coprire: «pronto» sarebbe
    vero a vuoto, ed è la risposta più pericolosa da dare."""
    catalogo = carica_catalogo()
    client, _ = _client(monkeypatch, celle=0, copertura={v.id: 0 for v in catalogo.voci})
    corpo = client.get("/api/installazione/stato").json()
    assert not any(p["pronto"] for p in corpo["pericoli"])


def test_lo_stato_dice_se_le_azioni_sono_abilitate(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(monkeypatch, token=None)
    assert client.get("/api/installazione/stato").json()["azioni_abilitate"] is False


def test_mancanti_conta_solo_gli_essenziali() -> None:
    catalogo = carica_catalogo()
    senza_strade = {v.id: 1 for v in catalogo.voci if v.id != "strade"}
    regioni = {"it-puglia": senza_strade}
    assert all(
        not ids for ids in mancanti(catalogo, totali=senza_strade, per_regione=regioni).values()
    )
    assert mancanti(catalogo, totali={}, per_regione={})[HazardType.WILDFIRE] == ["dtm", "corine"]


def test_un_dato_in_una_sola_regione_non_rende_pronto_il_pericolo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il DTM caricato per la Puglia e non per la Basilicata: «pronto» direbbe
    che la mappa incendio distingue i versanti anche dove è uniforme."""
    catalogo = carica_catalogo()
    tutto = {v.id: 1000 for v in catalogo.voci}
    per_cella = {v.id for v in catalogo.voci if v.misura.colonna is not None}
    piena = {k: n for k, n in tutto.items() if k in per_cella}
    client, _ = _client(
        monkeypatch,
        copertura=tutto,
        per_regione={"it-puglia": piena, "it-basilicata": piena | {"dtm": 0}},
    )
    corpo = client.get("/api/installazione/stato").json()
    pericoli = {p["pericolo"]: p for p in corpo["pericoli"]}
    assert pericoli["wildfire"]["mancano"] == ["dtm"]
    assert not pericoli["landslide"]["pronto"]
    assert {v["id"]: v for v in corpo["voci"]}["dtm"]["regioni_senza"] == ["it-basilicata"]
