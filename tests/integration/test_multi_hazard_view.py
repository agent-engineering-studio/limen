"""Vista «quadro unico» e sua superficie di tile (issue #58, migrazione 037).

Tre proprietà che solo il database può dimostrare. Una riga per cella, non
una per (cella, pericolo): una sorgente di tile che ne dà due disegna la
stessa cella due volte con due colori. Il pericolo peggiore scelto per
**classe**, non per ordine alfabetico né per punteggio grezzo, perché i
punteggi di pericoli diversi non sono confrontabili fra loro mentre le classi
sì. E il nome del layer dentro il tile, che se non combacia con il
`source-layer` della mappa produce tile validi e una mappa vuota — il guasto
silenzioso già visto in #87.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import asyncpg
import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.map_views_repo import refresh_latest_risk

pytestmark = pytest.mark.integration

_AOI_ID = "mh-test-aoi"
_CELLS = ("mh-cell-1", "mh-cell-2")


async def _seed(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        INSERT INTO aoi (id, name, kind, geom)
        VALUES ($1, 'Multi hazard test', 'region',
                ST_Multi(ST_MakeEnvelope(16.8, 41.1, 16.9, 41.2, 4326)))
        ON CONFLICT (id) DO NOTHING
        """,
        _AOI_ID,
    )
    for i, cell_id in enumerate(_CELLS):
        lon = 16.81 + i * 0.01
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 0, $3,
                    ST_MakeEnvelope($4::float8, 41.11, $4::float8 + 0.01, 41.12, 4326),
                    1.0)
            ON CONFLICT (id) DO NOTHING
            """,
            cell_id,
            _AOI_ID,
            i,
            lon,
        )


async def _assess(
    conn: asyncpg.Connection,
    cell_id: str,
    *,
    hazard: HazardType,
    score: float,
    level: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO risk_assessments (
            cell_id, computed_at, hazard_type, horizon, score, class,
            factors, pipeline_version
        ) VALUES ($1, now(), $2, '24h', $3, $4,
                  jsonb_build_object('e', 0.5), 'test')
        """,
        cell_id,
        hazard.value,
        score,
        level,
    )


@pytest.fixture()
async def three_hazards(reset_db: None) -> AsyncIterator[None]:
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = true")
        await _seed(conn)
        # Cella 1: l'incendio è la classe peggiore, ma il *punteggio* più alto
        # è quello della frana. Se la vista ordinasse per punteggio darebbe la
        # risposta sbagliata, ed è esattamente il caso reale: i cutoff sono
        # per pericolo, quindi 0.44 è High per l'incendio e Low per la frana.
        await _assess(conn, _CELLS[0], hazard=HazardType.WILDFIRE, score=0.44, level="High")
        await _assess(conn, _CELLS[0], hazard=HazardType.LANDSLIDE, score=0.51, level="Low")
        await _assess(conn, _CELLS[0], hazard=HazardType.FLOOD, score=0.10, level="None")
        # Cella 2: due pericoli High insieme — il caso che la regola
        # dell'alert congiunto cerca.
        await _assess(conn, _CELLS[1], hazard=HazardType.FLOOD, score=0.70, level="High")
        await _assess(conn, _CELLS[1], hazard=HazardType.LANDSLIDE, score=0.68, level="High")
    async with acquire() as conn:
        await conn.execute("UPDATE mv_refresh_state SET refreshed_at = 'epoch'::timestamptz")
    await refresh_latest_risk()
    yield
    # `hazards` non è in reset_db: senza il ripristino ogni test successivo
    # della sessione vedrebbe tre pericoli abilitati.
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = (hazard = 'landslide')")
        await conn.execute("UPDATE mv_refresh_state SET refreshed_at = 'epoch'::timestamptz")
    await refresh_latest_risk()


async def test_one_row_per_cell(three_hazards: None) -> None:
    async with acquire() as conn:
        per_cell = await conn.fetch(
            "SELECT cell_id, count(*) AS n FROM v_multi_hazard WHERE aoi_id = $1 GROUP BY cell_id",
            _AOI_ID,
        )
        in_source = await conn.fetchval(
            "SELECT count(*) FROM mv_latest_risk WHERE aoi_id = $1", _AOI_ID
        )
    assert {r["cell_id"] for r in per_cell} == set(_CELLS)
    assert all(r["n"] == 1 for r in per_cell)
    # La sorgente ne ha tre per cella: l'aggregazione è reale, non un caso.
    assert in_source == len(_CELLS) * 3


async def test_worst_is_by_class_not_by_score(three_hazards: None) -> None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT worst_hazard, worst_level, worst_score, hazards_scored, "
            "hazards_at_moderate, hazards_at_high "
            "FROM v_multi_hazard WHERE cell_id = $1",
            _CELLS[0],
        )
    assert row is not None
    assert row["worst_hazard"] == "wildfire"
    assert row["worst_level"] == "High"
    assert row["worst_score"] == pytest.approx(0.44)
    assert row["hazards_scored"] == 3
    assert list(row["hazards_at_moderate"]) == ["wildfire"]
    assert list(row["hazards_at_high"]) == ["wildfire"]


async def test_two_hazards_over_threshold_are_both_listed(three_hazards: None) -> None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT hazards_at_high FROM v_multi_hazard WHERE cell_id = $1", _CELLS[1]
        )
        joint = await conn.fetchval(
            "SELECT count(*) FROM v_multi_hazard "
            "WHERE aoi_id = $1 AND array_length(hazards_at_high, 1) >= 2",
            _AOI_ID,
        )
    assert row is not None
    assert list(row["hazards_at_high"]) == ["flood", "landslide"]
    assert joint == 1


async def test_tile_carries_the_layer_name_the_map_asks_for(three_hazards: None) -> None:
    async with acquire() as conn:
        # Gli indici si calcolano dalla geometria seminata: scriverli a mano
        # dà un tile vuoto e un test che fallisce per il motivo sbagliato.
        tile = await conn.fetchval(
            """
            WITH c AS (
                SELECT ST_Centroid(geom) AS g FROM grid_cells WHERE id = $1
            ), t AS (
                SELECT 12 AS z,
                       floor((ST_X(g) + 180) / 360 * 4096)::int AS x,
                       floor(
                           (1 - ln(tan(radians(ST_Y(g))) + 1 / cos(radians(ST_Y(g))))
                            / pi()) / 2 * 4096
                       )::int AS y
                FROM c
            )
            SELECT public.multi_hazard_at(z, x, y) FROM t
            """,
            _CELLS[0],
        )
    assert tile
    # Il nome del layer MVT non è il path della funzione: la mappa punta
    # `source-layer` su questo, e se non c'è la mappa è vuota senza errori.
    assert b"public.v_multi_hazard" in tile
    assert b"worst_hazard" in tile and b"worst_level" in tile


async def test_disabled_hazard_leaves_the_view(three_hazards: None) -> None:
    """`mv_latest_risk` incrocia solo i pericoli abilitati, e la vista eredita."""
    async with acquire() as conn:
        await conn.execute("UPDATE hazards SET enabled = (hazard <> 'wildfire')")
        await conn.execute("UPDATE mv_refresh_state SET refreshed_at = 'epoch'::timestamptz")
    await refresh_latest_risk()
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT worst_hazard, worst_level, hazards_scored "
            "FROM v_multi_hazard WHERE cell_id = $1",
            _CELLS[0],
        )
    assert row is not None
    assert row["hazards_scored"] == 2
    # Senza l'incendio la classe peggiore della cella scende a Low.
    assert row["worst_level"] == "Low"
    assert row["worst_hazard"] == "landslide"
