"""Gli eventi MCP letti a cursore dal database vero (#371)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from limen.core import eventi
from limen.data.db import acquire
from limen.data.repos import eventi_repo

pytestmark = pytest.mark.integration

ADESSO = datetime.now(UTC).replace(microsecond=0)


async def _prepara() -> None:
    async with acquire() as conn:
        await conn.execute("SELECT ensure_partitions('risk_assessments', 3)")
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ('it-ev', 'Ev', 'region',"
            " ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))"
        )
        await conn.execute(
            "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) VALUES"
            " ('c-ev', 'it-ev', 0, 0, ST_MakeEnvelope(15, 41, 15.01, 41.01, 4326), 1)"
        )


async def _valutazione(ore_fa: float, classe: str, misurata: bool | None = True) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO risk_assessments (cell_id, computed_at, hazard_type, horizon, score,"
            " class, pipeline_version, measured) VALUES ('c-ev', $1, 'flood', '24h', 0.5, $2,"
            " 'test', $3)",
            ADESSO - timedelta(hours=ore_fa),
            classe,
            misurata,
        )


async def _tutti(nome: str, cursore: str, **kw: Any) -> dict[str, Any]:
    return await eventi_repo.poll(nome, {"hazard": "flood"}, cursore, adesso=ADESSO, **kw)


async def test_cambi_di_classe_e_non_misurato_dopo_il_cursore(
    reset_db: None, pg_pool: object
) -> None:
    await _prepara()
    inizio = eventi.codifica(eventi.Posizione(t=ADESSO - timedelta(hours=10), id=0))
    await _valutazione(9, "Low")
    await _valutazione(8, "High")  # Low → High: evento
    await _valutazione(7, "High")  # battito: niente
    await _valutazione(6, "Low", misurata=False)  # High → Low e non misurato
    await _valutazione(5, "Low", misurata=False)  # resta non misurato: niente
    await _valutazione(0.1, "VeryHigh")  # dentro il margine: non ancora

    cambi = await _tutti(eventi.CAMBIO_CLASSE, inizio)
    assert [(e["data"]["from"], e["data"]["to"]) for e in cambi["events"]] == [
        ("Low", "High"),
        ("High", "Low"),
    ]
    assert cambi["events"][0]["data"]["attribuzione"].startswith("Contains modified Copernicus")
    assert not cambi["truncated"] and not cambi["hasMore"]

    non_misurate = await _tutti(eventi.NON_MISURATO, inizio)
    assert len(non_misurate["events"]) == 1

    # Il cursore restituito è avanzato fino al margine: il cambio dentro il
    # margine arriva al giro dopo, una volta sola.
    dopo = await eventi_repo.poll(
        eventi.CAMBIO_CLASSE,
        {"hazard": "flood"},
        cambi["cursor"],
        adesso=ADESSO + eventi_repo.MARGINE,
    )
    assert [e["data"]["to"] for e in dopo["events"]] == ["VeryHigh"]


async def test_pagine_e_cursori_vecchi(reset_db: None, pg_pool: object) -> None:
    await _prepara()
    inizio = eventi.codifica(eventi.Posizione(t=ADESSO - timedelta(hours=10), id=0))
    for i, classe in enumerate(["Low", "High", "Low", "High"]):
        await _valutazione(9 - i, classe)
    prima = await _tutti(eventi.CAMBIO_CLASSE, inizio, max_events=2)
    assert len(prima["events"]) == 2 and prima["hasMore"] and prima["nextPollMs"] == 0
    seconda = await _tutti(eventi.CAMBIO_CLASSE, prima["cursor"], max_events=2)
    assert len(seconda["events"]) == 1 and not seconda["hasMore"]
    assert {e["eventId"] for e in prima["events"]}.isdisjoint(
        e["eventId"] for e in seconda["events"]
    )
    # Un cursore di dieci ore fa con maxAgeMs di sei ore e mezza: si riparte
    # da lì, e si salta il cambio delle sette ore fa.
    vecchio = await _tutti(eventi.CAMBIO_CLASSE, inizio, max_age_ms=int(3_600_000 * 6.5))
    assert vecchio["truncated"]
    assert [e["data"]["to"] for e in vecchio["events"]] == ["High"]


async def test_le_allerte_spedite(reset_db: None, pg_pool: object) -> None:
    await _prepara()
    partenza = await eventi_repo.poll(eventi.ALLERTA, None, None, adesso=ADESSO)
    assert partenza["events"] == []
    async with acquire() as conn:
        for livello in ("Moderate", "High"):
            await conn.execute(
                "INSERT INTO alert_dispatches (cell_id, aoi_id, level, score, priority,"
                " dispatched_at, hazard_type) VALUES ('c-ev', 'it-ev', $1, 0.8, 1, $2,"
                " 'landslide')",
                livello,
                ADESSO + timedelta(minutes=1),
            )
    alte = await eventi_repo.poll(
        eventi.ALLERTA, {"min_level": "High"}, partenza["cursor"], adesso=ADESSO
    )
    assert [e["data"]["level"] for e in alte["events"]] == ["High"]
    assert alte["events"][0]["data"]["attribuzione"] is None
