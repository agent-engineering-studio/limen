"""I comuni che non contengono il centro di nessuna cella (#152).

Atrani è più piccolo di una cella da 1 km²: con l'assegnazione per centro
non ne riceveva nessuna, e non aveva né punteggio né riga nella lista. Ora
legge le celle che lo intersecano, senza togliere niente ai vicini.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from limen.data.db import acquire

pytestmark = pytest.mark.integration

_AOI = "it-minuscoli"


@pytest.fixture()
async def seeded(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom)
            VALUES ($1, 'Minuscoli', 'region',
                    ST_Multi(ST_MakeEnvelope(14.0, 40.0, 14.1, 40.1, 4326)))
            """,
            _AOI,
        )
        # Due celle affiancate; il comune grande contiene entrambi i centri,
        # il minuscolo sta a cavallo del bordo senza contenerne nessuno.
        for i, x0 in enumerate((14.00, 14.01)):
            await conn.execute(
                """
                INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
                VALUES ($1, $2, 0, $3,
                        ST_MakeEnvelope($4::float8, 40.0, $4::float8 + 0.01, 40.01, 4326), 1.0)
                """,
                f"{_AOI}|0|{i}",
                _AOI,
                i,
                x0,
            )
        for istat, nome, geom in (
            ("099100", "Grande", "ST_MakeEnvelope(14.0, 40.0, 14.02, 40.01, 4326)"),
            ("099101", "Minuscolo", "ST_MakeEnvelope(14.008, 40.003, 14.012, 40.006, 4326)"),
        ):
            await conn.execute(
                f"""
                INSERT INTO comuni (istat_code, name, aoi_id, geom)
                VALUES ($1, $2, $3, ST_Multi({geom}))
                ON CONFLICT (istat_code) DO NOTHING
                """,
                istat,
                nome,
                _AOI,
            )
        await conn.execute(
            """
            INSERT INTO cell_comune (cell_id, istat_code)
            SELECT g.id, c.istat_code FROM grid_cells g
            JOIN comuni c ON ST_Contains(c.geom, g.centroid)
            WHERE g.aoi_id = $1
            ON CONFLICT (cell_id) DO NOTHING
            """,
            _AOI,
        )
    yield
    async with acquire() as conn:
        await conn.execute("DELETE FROM cell_comune_extra WHERE istat_code IN ('099100', '099101')")
        await conn.execute("DELETE FROM cell_comune WHERE istat_code IN ('099100', '099101')")
        await conn.execute("DELETE FROM comuni WHERE istat_code IN ('099100', '099101')")


async def test_il_comune_minuscolo_legge_le_celle_che_lo_intersecano(seeded: None) -> None:
    async with acquire() as conn:
        senza = await conn.fetchval("SELECT count(*) FROM cell_comune WHERE istat_code = '099101'")
        assert senza == 0
        await conn.execute("SELECT refresh_cell_comune_extra()")
        sue = await conn.fetch(
            "SELECT cell_id FROM cell_comune_tutte WHERE istat_code = '099101' ORDER BY 1"
        )
        grande = await conn.fetchval(
            "SELECT count(*) FROM cell_comune_tutte WHERE istat_code = '099100'"
        )
    assert [r["cell_id"] for r in sue] == [f"{_AOI}|0|0", f"{_AOI}|0|1"]
    # Il vicino non perde niente: le sue due celle restano sue.
    assert grande == 2
