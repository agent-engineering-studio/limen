"""Lo stato corrente della mappa si aggiorna scrivendo, non rigenerando (#125).

`mv_latest_risk` ricavava l'ultimo punteggio per cella ordinando tutta
`risk_assessments` — diciannove milioni di righe al giorno per produrne
937.000, oltre venti minuti contro un debounce di cinque. Ora la riga la
scrive lo stesso passo che persiste lo sweep, e la vista la legge per
chiave. Questi test fissano le due proprietà che rendono valido il cambio:
la mappa è aggiornata **senza** nessun refresh, e una riga vecchia non
sovrascrive una recente.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.data.db import acquire

pytestmark = pytest.mark.anyio


async def _cell(conn: object, cell_id: str = "cell-125") -> None:
    await conn.execute(  # type: ignore[attr-defined]
        """
        INSERT INTO aoi (id, name, geom)
        VALUES ('it-test-125', 'Test 125',
                ST_GeomFromText('POLYGON((10 45,10.1 45,10.1 45.1,10 45.1,10 45))', 4326))
        ON CONFLICT (id) DO NOTHING
        """
    )
    await conn.execute(  # type: ignore[attr-defined]
        """
        INSERT INTO grid_cells (id, aoi_id, geom, centroid, area_km2)
        VALUES ($1, 'it-test-125',
                ST_GeomFromText('POLYGON((10 45,10.01 45,10.01 45.01,10 45.01,10 45))', 4326),
                ST_GeomFromText('POINT(10.005 45.005)', 4326), 1.0)
        ON CONFLICT (id) DO NOTHING
        """,
        cell_id,
    )


async def _upsert(conn: object, cell_id: str, score: float, when: datetime) -> None:
    await conn.execute(  # type: ignore[attr-defined]
        """
        INSERT INTO latest_risk (cell_id, hazard_type, score, class, horizon,
                                 pipeline_version, computed_at, factors, explanation)
        VALUES ($1, 'landslide', $2, 'Moderate', '24h', 'test', $3, '{}'::jsonb, '{}'::jsonb)
        ON CONFLICT (cell_id, hazard_type) DO UPDATE
        SET score = EXCLUDED.score, computed_at = EXCLUDED.computed_at
        WHERE latest_risk.computed_at <= EXCLUDED.computed_at
        """,
        cell_id,
        score,
        when,
    )


async def test_the_view_shows_the_score_without_any_refresh(reset_db: None) -> None:
    now = datetime.now(UTC)
    async with acquire() as conn:
        await _cell(conn)
        await _upsert(conn, "cell-125", 0.42, now)
        # Nessuna chiamata a refresh_mv_latest_risk(): è il punto.
        score = await conn.fetchval(
            "SELECT risk_score FROM mv_latest_risk"
            " WHERE cell_id = $1 AND hazard_type = 'landslide'",
            "cell-125",
        )
    assert score == pytest.approx(0.42)


async def test_an_older_row_does_not_overwrite_a_newer_one(reset_db: None) -> None:
    now = datetime.now(UTC)
    async with acquire() as conn:
        await _cell(conn)
        await _upsert(conn, "cell-125", 0.80, now)
        await _upsert(conn, "cell-125", 0.10, now - timedelta(hours=3))
        score = await conn.fetchval(
            "SELECT score FROM latest_risk WHERE cell_id = $1 AND hazard_type = 'landslide'",
            "cell-125",
        )
    assert score == pytest.approx(0.80)


async def test_a_cell_never_scored_is_still_on_the_map(reset_db: None) -> None:
    # Il CROSS JOIN con i pericoli abilitati: una cella senza valutazione
    # esiste comunque, con punteggio nullo. Era così anche prima ed è ciò
    # che permette alla mappa di disegnare tutto il territorio.
    async with acquire() as conn:
        await _cell(conn, "cell-125-vuota")
        row = await conn.fetchrow(
            "SELECT risk_score FROM mv_latest_risk"
            " WHERE cell_id = $1 AND hazard_type = 'landslide'",
            "cell-125-vuota",
        )
    assert row is not None
    assert row["risk_score"] is None
