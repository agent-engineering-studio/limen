"""L'esposizione ISPRA per comune: dalla risposta di IdroGEO alla riga."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from limen.integrations.idrogeo import esposizione

# Ridotta dalla risposta reale di /api/pir/comuni/72006 (Bari, 2026-11-03).
_BARI: dict[str, Any] = {
    "uid": 72006,
    "nome": "Bari",
    "pop_res021": 315948,
    "popfr_p3p4": 484,
    "popfrp3p4p": 0.153,
    "pop_idr_p2": 4037,
    "popidp2_p": 1.278,
    "ed_tot": 19815,
    "im_tot": 29166,
}


def test_la_riga_di_un_comune() -> None:
    riga = esposizione.da_indicatori(_BARI)
    assert riga is not None
    # Il PRO_COM a sei cifre di `comuni`, non il numero di ISPRA.
    assert riga.istat_code == "072006"
    assert (riga.pop_frana_p3p4, riga.pop_frana_p3p4_pct) == (484, 0.153)
    assert (riga.pop_idraulica_p2, riga.pop_idraulica_p2_pct) == (4037, 1.278)
    assert (riga.pop_residenti, riga.edifici, riga.imprese) == (315948, 19815, 29166)
    assert riga.indicatori is _BARI


def test_un_dato_mancante_resta_none() -> None:
    riga = esposizione.da_indicatori({"uid": 1001, "nome": "Agliè", "popfr_p3p4": None})
    assert riga is not None
    assert riga.pop_frana_p3p4 is None and riga.pop_residenti is None
    assert esposizione.da_indicatori({"nome": "senza codice"}) is None


def test_la_cartella_sta_sotto_i_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", "/var/lib/limen/datasets")
    assert esposizione.cartella() == Path("/var/lib/limen/datasets/idrogeo")


class _Repo:
    def __init__(self) -> None:
        self.versioni: set[str] = set()
        self.scritte: list[Any] = []

    async def find(self, _s: str, _d: str, versione: str) -> object | None:
        return object() if versione in self.versioni else None

    async def record(self, *, version: str, **_kw: object) -> int:
        self.versioni.add(version)
        return 7

    async def sostituisci(self, righe: list[Any], *, version_id: int) -> int:
        assert version_id == 7
        self.scritte.append(list(righe))
        return len(righe)


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> _Repo:
    finto = _Repo()
    monkeypatch.setattr(esposizione.dataset_versions_repo, "find", finto.find)
    monkeypatch.setattr(esposizione.dataset_versions_repo, "record", finto.record)
    monkeypatch.setattr(esposizione.esposizione_comuni_repo, "sostituisci", finto.sostituisci)
    return finto


def _risponde(monkeypatch: pytest.MonkeyPatch, dati: list[dict[str, Any]]) -> list[timedelta]:
    chieste: list[timedelta] = []

    async def municipalities(
        _self: object, summary: str, _directory: Path, *, max_age: timedelta
    ) -> list[dict[str, Any]]:
        assert summary == "pir"
        chieste.append(max_age)
        return dati

    monkeypatch.setattr(esposizione.IdroGEO, "municipalities", municipalities)
    return chieste


async def test_si_scrive_solo_quando_ispra_cambia(
    repo: _Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    chieste = _risponde(monkeypatch, [_BARI, {"uid": 1001, "nome": "Agliè", "popfr_p3p4": 12}])
    primo = await esposizione.sync_esposizione()
    assert primo == {"esito": "aggiornata", "comuni": 2, "residenti_frana_p3p4": 496}
    assert chieste == [esposizione.MAX_AGE]
    assert [r.istat_code for r in repo.scritte[0]] == ["072006", "001001"]

    # La notte dopo: stessi indicatori, nessuna scrittura.
    assert await esposizione.sync_esposizione() == {"esito": "invariata", "comuni": 2}
    assert len(repo.scritte) == 1


async def test_un_elenco_vuoto_non_svuota_la_tabella(
    repo: _Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    _risponde(monkeypatch, [])
    with pytest.raises(RuntimeError, match="nessun comune"):
        await esposizione.sync_esposizione()
    assert repo.scritte == []
