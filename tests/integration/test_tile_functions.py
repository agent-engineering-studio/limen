"""Le tile di ogni pericolo leggono lo stato corrente.

Il selettore mostrava i tre pericoli ma non disegnava nessuna cella per due
di essi: `risk_at()` e `multi_hazard_at()` erano rimaste sullo schema di
prima del #125 e attraversavano lo storico a ogni tile — misurati oltre 120
secondi per una. Questi test fissano il contratto che la mappa si aspetta:
una tile non vuota per ogni pericolo, il filtro che filtra davvero, e il
quadro unico che sceglie il peggiore.
"""

from __future__ import annotations

import pytest

from limen.data.db import acquire

_AOI = "it-test-tile"
_CELL = "cella-tile"
# Riquadro che contiene la cella: z9 su Roma, le stesse coordinate che la
# mappa chiede aprendosi.
_Z, _X, _Y = 9, 273, 190


async def _seed(punteggi: dict[str, tuple[float, str]]) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO aoi (id, name, kind, geom)
            VALUES ($1, 'tile test', 'region',
                    ST_GeomFromText(
                        'POLYGON((12.4 41.8,12.6 41.8,12.6 42.0,12.4 42.0,12.4 41.8))', 4326))
            ON CONFLICT (id) DO NOTHING
            """,
            _AOI,
        )
        await conn.execute(
            """
            INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)
            VALUES ($1, $2, 1, 1,
                    ST_GeomFromText(
                        'POLYGON((12.49 41.89,12.51 41.89,12.51 41.91,'
                        '12.49 41.91,12.49 41.89))', 4326),
                    1.0)
            ON CONFLICT (id) DO NOTHING
            """,
            _CELL,
            _AOI,
        )
        for hazard, (score, classe) in punteggi.items():
            await conn.execute(
                """
                INSERT INTO latest_risk (cell_id, hazard_type, score, class, horizon,
                                         pipeline_version, computed_at, factors, explanation,
                                         history_at)
                VALUES ($1, $2, $3, $4, '24h', 'test', now(), '{}'::jsonb, '{}'::jsonb, now())
                ON CONFLICT (cell_id, hazard_type) DO UPDATE
                SET score = EXCLUDED.score, class = EXCLUDED.class
                """,
                _CELL,
                hazard,
                score,
                classe,
            )


async def test_ogni_pericolo_ha_la_sua_tile(reset_db: None, pg_pool: object) -> None:
    await _seed({"landslide": (0.20, "Low"), "wildfire": (0.60, "High")})
    async with acquire() as conn:
        for hazard in ("landslide", "wildfire"):
            tile = await conn.fetchval(
                "SELECT risk_at($1, $2, $3, 0, $4::hazard_type)", _Z, _X, _Y, hazard
            )
            assert tile, f"tile vuota per {hazard}: la mappa non disegnerebbe niente"


async def test_il_filtro_per_pericolo_filtra(reset_db: None, pg_pool: object) -> None:
    # Solo le frane hanno una valutazione: la tile dell'incendio deve essere
    # vuota, non contenere le celle delle frane.
    await _seed({"landslide": (0.20, "Low")})
    async with acquire() as conn:
        frana = await conn.fetchval(
            "SELECT risk_at($1, $2, $3, 0, 'landslide'::hazard_type)", _Z, _X, _Y
        )
        incendio = await conn.fetchval(
            "SELECT risk_at($1, $2, $3, 0, 'wildfire'::hazard_type)", _Z, _X, _Y
        )
    assert frana
    assert not incendio


async def test_il_quadro_unico_sceglie_il_peggiore(reset_db: None, pg_pool: object) -> None:
    await _seed({"landslide": (0.20, "Low"), "wildfire": (0.60, "High")})
    async with acquire() as conn:
        tile = await conn.fetchval("SELECT multi_hazard_at($1, $2, $3)", _Z, _X, _Y)
    assert tile
    # Il contenuto della tile è binario MVT: quello che si può affermare qui
    # senza un decodificatore è che esiste. La scelta del peggiore è
    # verificata sulla vista in `test_multi_hazard_view.py`.


async def test_una_tile_lontana_dalle_celle_resta_vuota(reset_db: None, pg_pool: object) -> None:
    # Il filtro spaziale deve filtrare: senza, ogni tile conterrebbe tutte le
    # celle d'Italia e la mappa disegnerebbe la stessa cosa ovunque.
    await _seed({"landslide": (0.20, "Low")})
    async with acquire() as conn:
        lontana = await conn.fetchval("SELECT risk_at(9, 260, 175, 0, 'landslide'::hazard_type)")
    assert not lontana


async def test_il_cursore_del_tempo_non_esplode(reset_db: None, pg_pool: object) -> None:
    # Il ramo storico ha una forma diversa (attraversa `risk_assessments`) e
    # va esercitato: senza righe nello storico la tile è vuota, ma la
    # funzione deve rispondere.
    await _seed({"landslide": (0.20, "Low")})
    async with acquire() as conn:
        tile = await conn.fetchval(
            "SELECT risk_at($1, $2, $3, 24, 'landslide'::hazard_type)", _Z, _X, _Y
        )
    assert tile is None or isinstance(tile, bytes)


@pytest.mark.parametrize("hazard", ["landslide", "flood", "wildfire"])
async def test_una_cella_tutta_a_zero_compare_lo_stesso(
    reset_db: None, pg_pool: object, hazard: str
) -> None:
    # Classe «None» non è «nessun dato»: la cella esiste, vale zero, e deve
    # comparire sulla mappa col suo colore chiaro. Sparire vorrebbe dire
    # mostrare un buco dove c'è una risposta.
    await _seed({hazard: (0.0, "None")})
    async with acquire() as conn:
        tile = await conn.fetchval(
            "SELECT risk_at($1, $2, $3, 0, $4::hazard_type)", _Z, _X, _Y, hazard
        )
    assert tile
