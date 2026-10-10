"""I contributi degli esperti sul database vero: i numeri della cella arrivano nella mail."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from limen.api.endpoints import contributi as contributi_ep
from limen.config.settings import ContributiSettings, Settings
from limen.core import contributi
from limen.data.db import acquire

pytestmark = pytest.mark.integration

_CELLA = "it-prova|0|0"

_MODULO: dict[str, Any] = {
    "cell_id": _CELLA,
    "hazard": "landslide",
    "tipo": "frana_non_censita",
    "testo": "Sotto la strada provinciale c'è un corpo di frana attivo dal 2021.",
    "nome": "Maria Rossi",
    "email": "maria@example.org",
    "consenso": True,
    "compilato_in_ms": 30_000,
}


class _Deps:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings


@pytest.fixture()
async def cella(reset_db: None) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom)
            VALUES ('it-prova', 'Prova', 'region',
                    ST_Multi(ST_MakeEnvelope(16.0, 40.0, 16.5, 40.5, 4326)))
            """
        )
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, 'it-prova', 0, 0, ST_MakeEnvelope(16.1, 40.1, 16.11, 40.11, 4326), 1.0)
            """,
            _CELLA,
        )
        await conn.execute(
            """
            INSERT INTO latest_risk (cell_id, hazard_type, score, class, horizon,
                                     pipeline_version, computed_at, factors, measured)
            VALUES ($1, 'landslide', 0.31, 'Low', '24h', 'v1', now(), $2::jsonb, true)
            """,
            _CELLA,
            json.dumps({"S": 0.62, "M": 0.12}),
        )


def _client(monkeypatch: pytest.MonkeyPatch, inviate: list[dict[str, Any]]) -> httpx.AsyncClient:
    async def _invia(settings: Any, **kw: Any) -> bool:
        inviate.append(kw)
        return True

    monkeypatch.setattr(contributi_ep, "invia_testo", _invia)
    monkeypatch.setattr(contributi, "LIMITATORE", contributi.Limitatore())
    app = FastAPI()
    app.state.deps = _Deps(
        Settings(contributi=ContributiSettings(destinatari=["cura@example.org"]))
    )
    app.include_router(contributi_ep.router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_la_mail_porta_i_numeri_della_cella(
    cella: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    inviate: list[dict[str, Any]] = []
    async with _client(monkeypatch, inviate) as client:
        r = await client.post("/api/contributi", json=_MODULO)
    assert r.status_code == 201
    testo = inviate[0]["testo"]
    assert "Cella: it-prova|0|0 · regione it-prova" in testo
    assert "Coordinate: 40.10500, 16.10500" in testo
    assert "landslide: 0.31 (Low)" in testo
    assert "S = 0.62" in testo
    assert inviate[0]["rispondi_a"] == "maria@example.org"


async def test_cella_che_non_esiste(cella: None, monkeypatch: pytest.MonkeyPatch) -> None:
    inviate: list[dict[str, Any]] = []
    async with _client(monkeypatch, inviate) as client:
        r = await client.post("/api/contributi", json={**_MODULO, "cell_id": "it-prova|9|9"})
    assert r.status_code == 404
    assert inviate == []
