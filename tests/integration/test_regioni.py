"""Le regioni da monitorare: l'ordine dai numeri, il racconto dall'AI (#155)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import asyncpg
import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos import regioni_repo, spiegazioni_repo

pytestmark = pytest.mark.integration


async def _regione(
    conn: asyncpg.Connection,
    aoi: str,
    nome: str,
    x0: float,
    celle: list[tuple[str, float, str]],
) -> None:
    await conn.execute(
        """
        INSERT INTO aoi (id, name, kind, geom)
        VALUES ($1, $2, 'region',
                ST_Multi(ST_MakeEnvelope($3::float8, 40.0, $3::float8 + 0.5, 40.5, 4326)))
        """,
        aoi,
        nome,
        x0,
    )
    for i, (hazard, score, classe) in enumerate(celle):
        cell = f"{aoi}|0|{i}"
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 0, $3,
                    ST_MakeEnvelope($4::float8, 40.1, $4::float8 + 0.01, 40.11, 4326), 1.0)
            """,
            cell,
            aoi,
            i,
            x0 + 0.1 + i * 0.01,
        )
        await conn.execute(
            """
            INSERT INTO latest_risk (cell_id, hazard_type, score, class, horizon,
                                     pipeline_version, computed_at, factors, measured)
            VALUES ($1, $2::hazard_type, $3, $4, '24h', 'v1', now(), $5::jsonb, true)
            """,
            cell,
            hazard,
            score,
            classe,
            json.dumps({}),
        )


@pytest.fixture()
async def seeded(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await _regione(
            conn, "it-calma", "Calma", 10.0, [("landslide", 0.2, "Low"), ("flood", 0.05, "None")]
        )
        await _regione(
            conn,
            "it-esposta",
            "Esposta",
            12.0,
            [("flood", 0.8, "VeryHigh"), ("flood", 0.6, "High"), ("wildfire", 0.3, "Moderate")],
        )
    await spiegazioni_repo.scrivi(
        aoi_id="it-esposta",
        hazard=HazardType.FLOOD,
        run_id=1,
        livello="VeryHigh",
        modello="quality-cloud",
        ripiego=False,
        testo="Pioggia forte attesa.",
        analisi=None,
    )
    await spiegazioni_repo.scrivi(
        aoi_id="it-calma",
        hazard=HazardType.LANDSLIDE,
        run_id=1,
        livello="Low",
        modello="quality-cloud",
        ripiego=True,
        testo="Testo deterministico.",
        analisi=None,
    )
    yield


async def test_l_ordine_lo_decidono_i_numeri(seeded: None) -> None:
    regioni = [r for r in await regioni_repo.monitoraggio() if r["aoi_id"].startswith("it-")]
    nomi = [r["nome"] for r in regioni if r["aoi_id"] in ("it-calma", "it-esposta")]
    assert nomi == ["Esposta", "Calma"]
    esposta = next(r for r in regioni if r["aoi_id"] == "it-esposta")
    assert esposta["peggiore"]["hazard"] == "flood"
    assert esposta["peggiore"]["classe"] == "VeryHigh"
    assert esposta["pericoli"]["flood"]["alte"] == 2
    assert esposta["geom"]["type"] in ("Polygon", "MultiPolygon")


async def test_solo_le_spiegazioni_dell_ai_non_i_ripieghi(seeded: None) -> None:
    regioni = {r["aoi_id"]: r for r in await regioni_repo.monitoraggio()}
    assert regioni["it-esposta"]["spiegazioni"]["flood"]["testo"] == "Pioggia forte attesa."
    assert regioni["it-calma"]["spiegazioni"] == {}
