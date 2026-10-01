"""Il proxy delle tile inoltra `properties` (#154).

Le sorgenti a tabella dei livelli di contesto chiedono solo le colonne che
disegnano. Il proxy `/api/tiles` inoltrava soltanto `p_hazard` e
`hours_ago`: scartato `properties`, pg_tileserv restituiva tutte le colonne —
i JSON degli attributi, i metadati di caricamento — e le tile perdevano
l'ottimizzazione che le rendeva leggere.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api import dependencies
from limen.api.endpoints import tiles
from limen.integrations._http import SharedHttpClient


@pytest.fixture
def chiamate(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    viste: list[dict[str, Any]] = []

    class _Client:
        async def get(self, url: str, *, params: dict[str, str], timeout: float) -> httpx.Response:
            viste.append({"url": url, "params": params})
            return httpx.Response(
                200, content=b"\x1a\x00", headers={"content-type": "application/x-protobuf"}
            )

    async def _shared() -> _Client:
        return _Client()

    monkeypatch.setattr(SharedHttpClient, "get", _shared)
    return viste


def _app() -> TestClient:
    app = FastAPI()
    app.include_router(tiles.router)
    deps = SimpleNamespace(
        settings=SimpleNamespace(api=SimpleNamespace(pg_tileserv_url="http://pg_tileserv:7800"))
    )
    app.dependency_overrides[dependencies._get_deps] = lambda: deps
    return TestClient(app)


def test_properties_arriva_a_pg_tileserv(chiamate: list[dict[str, Any]]) -> None:
    r = _app().get("/api/tiles/public.fire_perimeters/8/139/96.pbf?properties=fire_date,area_ha")
    assert r.status_code == 200
    assert chiamate[0]["params"] == {"properties": "fire_date,area_ha"}


def test_senza_properties_non_si_inventa_niente(chiamate: list[dict[str, Any]]) -> None:
    # Le sorgenti a funzione non lo vogliono: `multi_hazard_at` risponde 400
    # a un parametro che non conosce.
    _app().get("/api/tiles/public.multi_hazard_at/8/139/96.pbf")
    assert chiamate[0]["params"] == {}


@pytest.mark.parametrize(
    "valore",
    ["fire_date;drop table", "a,,b", "Fire_Date", "x" * 201, "a, b"],
)
def test_solo_nomi_di_colonna(chiamate: list[dict[str, Any]], valore: str) -> None:
    """Validato, non inoltrato a occhi chiusi: un proxy che ripete ciò che gli
    arriva moltiplica a piacere le chiavi di cache di chi chiama."""
    r = _app().get(f"/api/tiles/public.fire_perimeters/8/1/1.pbf?properties={valore}")
    assert r.status_code == 422
    assert chiamate == []
