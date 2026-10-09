"""Comune REST endpoints — dispatch + 404 (repo stubbed, no DB)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import comuni as comuni_ep
from limen.data.repos import comune_risk as comune_risk_repo

_ROW = {
    "istat_code": "C001",
    "name": "Testville",
    "aoi_id": "it-test",
    "worst_hazard": "wildfire",
    "worst_class": "High",
    "max_score": 0.8,
    "n_cells": 2,
    "n_alert": 1,
    "counts": {"None": 0, "Low": 1, "Moderate": 0, "High": 1, "VeryHigh": 0},
    "exposure_rank": 0.9,
    "lon": 13.1,
    "lat": 46.5,
    "attention": 1.52,
    # I tre pericoli affiancati (migrazione 051): la riga li porta tutti,
    # anche quelli a zero.
    "hazards": {
        "landslide": {
            "class": "Moderate",
            "score": 0.44,
            "priority": 0.62,
            "n_cells": 2,
            "n_alert": 0,
        },
        "flood": {"class": "None", "score": 0.0, "priority": 0.0, "n_cells": 2, "n_alert": 0},
        "wildfire": {
            "class": "High",
            "score": 0.8,
            "priority": 1.52,
            "n_cells": 2,
            "n_alert": 1,
        },
    },
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _top(**kwargs: Any) -> list[dict[str, Any]]:
        return [_ROW]

    async def _detail(istat_code: str) -> dict[str, Any] | None:
        return {"comune": _ROW, "cells": []} if istat_code == "C001" else None

    monkeypatch.setattr(comune_risk_repo, "top_comuni", _top)
    monkeypatch.setattr(comune_risk_repo, "comune_detail", _detail)
    app = FastAPI()
    app.include_router(comuni_ep.router)
    return TestClient(app)


def test_list_comuni(client: TestClient) -> None:
    body = client.get("/api/comuni?aoi=it-test&limit=10").json()
    assert body["comuni"][0]["worst_class"] == "High"
    assert body["comuni"][0]["counts"]["High"] == 1


def test_la_riga_porta_tutti_i_pericoli(client: TestClient) -> None:
    """Non più a pericolo unico: prima l'endpoint rifiutava con 404 qualunque
    pericolo diverso dalle frane, e la colonna mostrava un badge per dirlo."""
    riga = client.get("/api/comuni").json()["comuni"][0]
    assert set(riga["hazards"]) == {"landslide", "flood", "wildfire"}
    assert riga["hazards"]["flood"]["class"] == "None"
    assert riga["worst_hazard"] == "wildfire"


def test_la_ricerca_arriva_al_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chi cerca il proprio comune deve trovarlo anche se è tranquillo: il
    termine va passato al repo, che senza di esso applicherebbe la soglia."""
    visti: dict[str, Any] = {}

    async def _top(**kwargs: Any) -> list[dict[str, Any]]:
        visti.update(kwargs)
        return []

    monkeypatch.setattr(comune_risk_repo, "top_comuni", _top)
    app = FastAPI()
    app.include_router(comuni_ep.router)
    TestClient(app).get("/api/comuni?q=Avezzano")
    assert visti["query"] == "Avezzano"


def test_il_pericolo_scelto_arriva_al_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scelto un pericolo nel quadro nazionale, la classifica si ordina su
    quello; senza, su tutti. Un nome fuori dall'enum è un 422."""
    visti: list[Any] = []

    async def _top(**kwargs: Any) -> list[dict[str, Any]]:
        visti.append(kwargs["hazard"])
        return []

    monkeypatch.setattr(comune_risk_repo, "top_comuni", _top)
    app = FastAPI()
    app.include_router(comuni_ep.router)
    c = TestClient(app)
    c.get("/api/comuni?hazard=wildfire")
    c.get("/api/comuni")
    assert visti == ["wildfire", None]
    assert c.get("/api/comuni?hazard=vulcano").status_code == 422


def test_l_ordine_sul_pericolo_scelto() -> None:
    """Il comune dove brucia sta sopra quello dove frana, se si guarda
    l'incendio; un pericolo non misurato non ha un numero e va in coda."""
    from limen.data.repos.comune_risk import _numero_ordine

    riga = {
        **_ROW,
        "forecast_attention": 0.9,
        "forecast": {"wildfire": {"class": "High", "score": 0.6, "priority": 0.7}},
    }
    riga["hazards"] = {**_ROW["hazards"], "flood": {**_ROW["hazards"]["flood"], "measured": False}}
    riga["hazards"]["wildfire"] = {**_ROW["hazards"]["wildfire"], "measured": True}
    assert _numero_ordine(riga, order="now", hazard=None) == 1.52
    assert _numero_ordine(riga, order="now", hazard="wildfire") == 1.52
    assert _numero_ordine(riga, order="now", hazard="flood") is None
    assert _numero_ordine(riga, order="forecast", hazard="wildfire") == 0.7
    assert _numero_ordine(riga, order="forecast", hazard="landslide") is None
    assert _numero_ordine(riga, order="forecast", hazard=None) == 0.9


def test_comune_detail_and_404(client: TestClient) -> None:
    assert client.get("/api/comune/C001").json()["comune"]["name"] == "Testville"
    assert client.get("/api/comune/NOPE").status_code == 404


def test_la_riga_porta_le_coordinate(client: TestClient) -> None:
    """Il centroide arriva fino alla risposta, o la mappa non si muove.

    Il campo c'era nel repo e non nel DTO, e `response_model` lo toglieva in
    silenzio: la colonna riceveva righe senza coordinate e cliccarle non
    faceva niente. Un campo che il repo produce e il DTO non dichiara sparisce
    senza un errore da nessuna parte, quindi lo verifica un test.
    """
    body = client.get("/api/comuni").json()["comuni"][0]
    assert body["lon"] == 13.1
    assert body["lat"] == 46.5


def test_il_confine_del_comune_arriva_con_il_riquadro(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il bordo serve a evidenziare il comune, il riquadro a inquadrarlo
    intero: uno zoom fisso tagliava Roma e lasciava Atrani un puntino."""

    async def _geom(istat_code: str) -> dict[str, object] | None:
        if istat_code != "065011":
            return None
        return {
            "type": "Feature",
            "properties": {"istat_code": "065011", "name": "Atrani"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[14.6, 40.6], [14.61, 40.6], [14.61, 40.61], [14.6, 40.6]]],
            },
            "bbox": [14.6, 40.6, 14.61, 40.61],
        }

    monkeypatch.setattr(comune_risk_repo, "comune_geometry", _geom)
    app = FastAPI()
    app.include_router(comuni_ep.router)

    with TestClient(app) as c:
        ok = c.get("/api/comune/065011/geometry")
        assert ok.status_code == 200
        assert ok.json()["bbox"] == [14.6, 40.6, 14.61, 40.61]
        assert ok.json()["properties"]["name"] == "Atrani"
        # I confini cambiano con un decreto, non con uno sweep.
        assert "max-age=86400" in ok.headers["cache-control"]
        assert c.get("/api/comune/999999/geometry").status_code == 404
