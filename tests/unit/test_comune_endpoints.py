"""Comune REST endpoints — dispatch + 404 (repo stubbed, no DB)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import comuni as comuni_ep

_ROW = {
    "istat_code": "C001",
    "name": "Testville",
    "aoi_id": "it-test",
    "worst_class": "High",
    "max_score": 0.8,
    "n_cells": 2,
    "n_alert": 1,
    "counts": {"None": 0, "Low": 1, "Moderate": 0, "High": 1, "VeryHigh": 0},
    "exposure_rank": 0.9,
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _top(**kwargs: Any) -> list[dict[str, Any]]:
        return [_ROW]

    async def _detail(istat_code: str) -> dict[str, Any] | None:
        return {"comune": _ROW, "cells": []} if istat_code == "C001" else None

    monkeypatch.setattr(comuni_ep.comune_risk, "top_comuni", _top)
    monkeypatch.setattr(comuni_ep.comune_risk, "comune_detail", _detail)
    app = FastAPI()
    app.include_router(comuni_ep.router)
    return TestClient(app)


def test_list_comuni(client: TestClient) -> None:
    body = client.get("/api/comuni?aoi=it-test&limit=10").json()
    assert body["comuni"][0]["worst_class"] == "High"
    assert body["comuni"][0]["counts"]["High"] == 1


def test_comune_detail_and_404(client: TestClient) -> None:
    assert client.get("/api/comune/C001").json()["comune"]["name"] == "Testville"
    assert client.get("/api/comune/NOPE").status_code == 404
