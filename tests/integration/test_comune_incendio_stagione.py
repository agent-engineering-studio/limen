"""L'incendio del comune, rispetto al solito per il mese (#155).

Le classi dell'incendio sono assolute, come quelle di EFFIS: FWI 24 è «alto»
ad agosto come a ottobre. La riga del comune porta l'FWI della cella peggiore
e a che percentile cade fra i giorni dello stesso mese nel nodo di
climatologia di quel punto — senza toccare il punteggio.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from limen.data.db import acquire
from limen.data.repos.comune_risk import _segnali_incendio

pytestmark = pytest.mark.integration

_AOI = "it-stagione"
_COMUNE = "099001"


@pytest.fixture()
async def seeded(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom)
            VALUES ($1, 'Stagione', 'region',
                    ST_Multi(ST_MakeEnvelope(16.4, 40.0, 16.6, 40.2, 4326)))
            """,
            _AOI,
        )
        await conn.execute(
            """
            INSERT INTO comuni (istat_code, name, aoi_id, geom)
            VALUES ($1, 'Montestagione', $2,
                    ST_Multi(ST_MakeEnvelope(16.4, 40.0, 16.6, 40.2, 4326)))
            ON CONFLICT (istat_code) DO NOTHING
            """,
            _COMUNE,
            _AOI,
        )
        for i, (score, fwi) in enumerate(((0.49, 24.0), (0.20, 10.0))):
            cell = f"{_AOI}|0|{i}"
            lon = 16.49 + i * 0.01
            await conn.execute(
                """
                INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
                VALUES ($1, $2, 0, $3,
                        ST_MakeEnvelope($4::float8, 40.09, $4::float8 + 0.01, 40.10, 4326), 1.0)
                """,
                cell,
                _AOI,
                i,
                lon,
            )
            await conn.execute(
                "INSERT INTO cell_comune (cell_id, istat_code) VALUES ($1, $2)", cell, _COMUNE
            )
            await conn.execute(
                """
                INSERT INTO latest_risk (cell_id, hazard_type, score, class, horizon,
                                         pipeline_version, computed_at, factors, measured)
                VALUES ($1, 'wildfire', $2, 'High', '24h', 'v1', now(), $3::jsonb, true)
                """,
                cell,
                score,
                json.dumps({"fire_weather": {"fwi": fwi, "day": "2026-10-06"}}),
            )
        # Ottobre al nodo (16.5, 40.0): i quantili 0, 5, …, 100 % vanno da 0 a
        # 40 a passi di 2, quindi FWI 24 sta al 60° percentile.
        await conn.execute(
            """
            INSERT INTO fwi_climatology (node_lon, node_lat, month, days, quantiles,
                                         year_from, year_to)
            VALUES (16.5, 40.0, 10, 310, $1::float8[], 2016, 2025)
            """,
            [float(2 * i) for i in range(21)],
        )
    yield
    async with acquire() as conn:
        await conn.execute("DELETE FROM fwi_climatology WHERE node_lon = 16.5 AND node_lat = 40.0")
        await conn.execute("DELETE FROM cell_comune WHERE istat_code = $1", _COMUNE)
        await conn.execute("DELETE FROM comuni WHERE istat_code = $1", _COMUNE)


async def test_la_cella_peggiore_porta_fwi_e_percentile_del_mese(seeded: None) -> None:
    async with acquire() as conn:
        segnali = await _segnali_incendio(conn, [_COMUNE])
    assert segnali == {_COMUNE: {"fwi": 24.0, "fwi_month": 10, "fwi_percentile": 60}}


async def test_senza_climatologia_il_percentile_e_ignoto(seeded: None) -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM fwi_climatology WHERE node_lon = 16.5 AND node_lat = 40.0")
        segnali = await _segnali_incendio(conn, [_COMUNE])
    assert segnali[_COMUNE]["fwi_percentile"] is None
