"""mv_comune_risk rollup semantics against real PostGIS."""

from __future__ import annotations

import pytest

from limen.data.db import acquire


async def _seed_minimal() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, geom) VALUES ('it-test','Test', "
            "ST_Multi(ST_GeomFromText('POLYGON((0 0,0 2,2 2,2 0,0 0))',4326)))"
        )
        for i, (x, cls, score, e) in enumerate([(0.5, "High", 0.8, 0.9), (1.5, "Low", 0.2, 0.1)]):
            cid = f"it-test|0|{i}"
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,'it-test',0,$2, ST_GeomFromText($3,4326), 1.0)",
                cid,
                i,
                f"POLYGON(({x} 0.4,{x} 0.6,{x + 0.1} 0.6,{x + 0.1} 0.4,{x} 0.4))",
            )
            await conn.execute(
                "INSERT INTO risk_assessments "
                "(cell_id, hazard_type, score, class, factors, computed_at, horizon, "
                " pipeline_version) "
                "VALUES ($1,'landslide',$2,$3, jsonb_build_object('e',$4::float), "
                "        now(), 'now','v1')",
                cid,
                score,
                cls,
                e,
            )
            # L'esposizione ora vive sulla cella e non nel breakdown delle
            # frane (migrazione 052): è una proprietà del posto, non del
            # pericolo, ed è ciò che pesa la priorità del comune.
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id, exposure_norm) VALUES ($1,$2) "
                "ON CONFLICT (cell_id) DO UPDATE SET exposure_norm = EXCLUDED.exposure_norm",
                cid,
                e,
            )
        await conn.execute(
            "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES "
            "('C001','Testville','it-test', "
            "ST_Multi(ST_GeomFromText('POLYGON((0 0,0 2,2 2,2 0,0 0))',4326)))"
        )
        await conn.execute(
            "INSERT INTO cell_comune (cell_id, istat_code) "
            "SELECT g.id, c.istat_code FROM grid_cells g JOIN comuni c "
            "ON ST_Contains(c.geom, g.centroid)"
        )


async def test_comune_rollup(reset_db: None) -> None:
    await _seed_minimal()
    async with acquire() as conn:
        # Righe seminate a mano: lo stato della mappa lo scrive il passo di
        # persistenza (#125), qui va ricostruito.
        await conn.execute("SELECT rebuild_latest_risk()")
        await conn.execute("SELECT refresh_mv_latest_risk()")  # also refreshes comune
        # Una riga per (comune, pericolo) dalla migrazione 051: qui si guarda
        # quella delle frane, che è il pericolo seminato.
        row = await conn.fetchrow(
            "SELECT * FROM mv_comune_risk WHERE istat_code='C001' AND hazard_type='landslide'"
        )
        pericoli = await conn.fetchval(
            "SELECT count(*) FROM mv_comune_risk WHERE istat_code='C001'"
        )
        tile = await conn.fetchrow("SELECT * FROM v_comune_tiles WHERE istat_code='C001'")
    assert row is not None
    assert row["worst_class"] == "High"  # worst cell drives the headline
    assert row["n_alert"] == 1  # one High+ cell
    assert row["n_cells"] == 2
    # `exposure_rank` è il massimo sulle celle del comune, non più la somma
    # del termine E delle sole celle in allerta: una cella sopra un paese
    # basta a rendere il comune un posto da guardare.
    assert float(row["exposure_rank"]) == pytest.approx(0.9)
    # E la priorità è il punteggio della cella peggiore pesato per la sua
    # esposizione — la stessa formula degli alert.
    assert float(row["priority"]) > float(row["max_score"])
    # Ogni pericolo abilitato ha la sua riga, anche senza celle valutate: una
    # colonna che sparisce non distingue «calmo» da «non calcolato».
    assert int(pericoli) >= 1
    # La mappa però ne vuole **una sola** per comune, altrimenti disegna
    # poligoni sovrapposti e il colore è quello dell'ultimo disegnato.
    assert tile is not None
    assert tile["worst_class"] == "High"
    assert tile["worst_hazard"] == "landslide"
