"""Registro EMS per comune (#713): km², CSV, attribuzione, endpoint (repo finto)."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shapely.geometry import box

from limen.api.endpoints import ems as ems_ep
from limen.core import ems_registro
from limen.core.ems_registro import Comune, Poligono, comuni_colpiti
from limen.data.repos import flood_events_repo
from limen.data.repos.flood_events_repo import (
    ActivationSummary,
    ComuneGeom,
    PoligonoOsservato,
)

_INIZIO = datetime(2023, 5, 16, 11, tzinfo=UTC)
_OSS = datetime(2023, 5, 17, 16, 56, tzinfo=UTC)
_FORMULA = "Contains modified Copernicus Emergency Management Service information, 2023"


def _comuni() -> list[Comune]:
    return [
        Comune("039014", "Ravenna", "it-emilia-romagna", box(0, 0, 1000, 1000)),
        Comune("039012", "Lugo", "it-emilia-romagna", box(1000, 0, 2000, 1000)),
        Comune("037006", "Bologna", "it-emilia-romagna", box(5000, 0, 6000, 1000)),
    ]


def test_km2_per_comune_con_unione() -> None:
    acqua = [
        Poligono("EMSR664-aoi01-DEL0", box(500, 0, 1500, 1000), _INIZIO, _OSS),
        # stesso campo ridisegnato da un'altra AOI: non raddoppia
        Poligono("EMSR664-aoi02-GRA0", box(500, 0, 1000, 1000), _INIZIO, None),
    ]
    righe = comuni_colpiti(acqua, _comuni())
    assert [r.istat_code for r in righe] == ["039012", "039014"]
    ravenna = next(r for r in righe if r.istat_code == "039014")
    assert ravenna.acqua_km2 == pytest.approx(0.5)
    assert ravenna.prodotti == ("EMSR664-aoi01-DEL0", "EMSR664-aoi02-GRA0")
    assert ravenna.osservato_dal == _OSS
    assert ravenna.inizio == _INIZIO


def test_csv_porta_attribuzione_su_ogni_riga() -> None:
    acqua = [Poligono("EMSR664-aoi01-DEL0", box(0, 0, 2000, 1000), _INIZIO, _OSS)]
    testo = ems_registro.registro_csv("EMSR664", comuni_colpiti(acqua, _comuni()))
    righe = list(csv.DictReader(io.StringIO(testo)))
    assert list(righe[0]) == list(ems_registro.COLONNE)
    assert len(righe) == 2
    assert {r["attribuzione"] for r in righe} == {_FORMULA}
    assert righe[0]["acqua_km2"] == "1.0"
    assert righe[0]["inizio_evento"] == "2023-05-16T11:00:00+00:00"


def test_json_avverte_che_non_e_un_allerta() -> None:
    acqua = [Poligono("EMSR664-aoi01-DEL0", box(0, 0, 1000, 1000), _INIZIO, _OSS)]
    out = ems_registro.registro_json("EMSR664", comuni_colpiti(acqua, _comuni()))
    assert out["attribuzione"] == _FORMULA
    assert "non un'allerta" in out["avvertenza"]
    assert out["acqua_km2"] == pytest.approx(1.0)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _acqua(codice: str) -> list[PoligonoOsservato]:
        if codice != "EMSR664":
            return []
        return [
            PoligonoOsservato("EMSR664-aoi01-DEL0-0-0", box(0, 0, 1000, 1000), _INIZIO, _OSS),
            # monitoraggio: fuori dal registro
            PoligonoOsservato("EMSR664-aoi01-DEL1-0-0", box(1000, 0, 2000, 1000), _INIZIO, _OSS),
        ]

    async def _comuni_geom(codice: str) -> list[ComuneGeom]:
        return [ComuneGeom(c.istat_code, c.nome, c.aoi_id, c.geom) for c in _comuni()]

    async def _sommario() -> list[ActivationSummary]:
        return [ActivationSummary("EMSR664", _INIZIO, 2, 2.0, "Emilia-Romagna")]

    monkeypatch.setattr(flood_events_repo, "acqua_osservata", _acqua)
    monkeypatch.setattr(flood_events_repo, "comuni_nel_riquadro", _comuni_geom)
    monkeypatch.setattr(flood_events_repo, "activations_summary", _sommario)
    monkeypatch.setattr(ems_registro, "_memoria", {})
    app = FastAPI()
    app.include_router(ems_ep.router)
    return TestClient(app)


def test_endpoint_attivazioni(client: TestClient) -> None:
    r = client.get("/api/ems/attivazioni")
    assert r.status_code == 200
    a = r.json()["attivazioni"][0]
    assert a["attivazione"] == "EMSR664"
    assert a["attribuzione"] == _FORMULA


def test_endpoint_comuni_json_e_csv(client: TestClient) -> None:
    r = client.get("/api/ems/attivazioni/emsr664/comuni")
    assert r.status_code == 200
    corpo = r.json()
    assert [c["istat_code"] for c in corpo["comuni"]] == ["039014"]
    assert corpo["attribuzione"] == _FORMULA
    c = client.get("/api/ems/attivazioni/EMSR664/comuni?formato=csv")
    assert c.status_code == 200
    assert c.headers["content-type"].startswith("text/csv")
    assert _FORMULA in c.text
    assert "EMSR664_comuni.csv" in c.headers["content-disposition"]


def test_endpoint_404(client: TestClient) -> None:
    assert client.get("/api/ems/attivazioni/EMSR000/comuni").status_code == 404


def test_registro_in_memoria(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.get("/api/ems/attivazioni/EMSR664/comuni").status_code == 200
    assert client.get("/api/ems/attivazioni/EMSR000/comuni").status_code == 404

    async def _rotto(codice: str) -> list[PoligonoOsservato]:
        raise AssertionError("il registro doveva venire dalla memoria")

    monkeypatch.setattr(flood_events_repo, "acqua_osservata", _rotto)
    assert client.get("/api/ems/attivazioni/EMSR664/comuni").status_code == 200
    assert "EMSR000" not in ems_registro._memoria


async def test_richieste_insieme_un_solo_calcolo(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.setattr(ems_registro, "_memoria", {})
    monkeypatch.setattr(ems_registro, "_in_corso", {})
    calcoli = 0

    async def _calcola(codice: str) -> list[ems_registro.ComuneColpito]:
        nonlocal calcoli
        calcoli += 1
        await asyncio.sleep(0.01)
        return []

    monkeypatch.setattr(ems_registro, "_calcola", _calcola)
    await asyncio.gather(*(ems_registro.registro("EMSR664") for _ in range(5)))
    assert calcoli == 1
