"""Lo step ``StaticFactors`` porta InSAR e suscettibilità nel bundle (#568).

Lo sfidante frane imparava le ``insar.*`` dai valori di
``cell_insar_features`` e al servizio le riceveva a zero, perché il bundle non
le portava. Qui contro un Postgres vero: la colonna giusta, dalla tabella
giusta, sulla cella giusta.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.agents.executors.static_factors import StaticFactorsExecutor
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire

pytestmark = pytest.mark.integration

AOI = "sf-insar-aoi"


async def test_il_bundle_porta_insar_e_suscettibilita(reset_db: None, pg_pool: object) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1, 'SF', 'region',"
            " ST_Multi(ST_MakeEnvelope(15.0, 40.0, 15.1, 40.1, 4326)))",
            AOI,
        )
        for i in (0, 1):
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2)"
                " VALUES ($1, $2, 0, $3::int,"
                " ST_MakeEnvelope(15.0 + $4, 40.0, 15.01 + $4, 40.01, 4326), 1.0)",
                f"{AOI}|0|{i}",
                AOI,
                i,
                i * 0.01,
            )
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id, slope_deg) VALUES ($1, 20.0)",
                f"{AOI}|0|{i}",
            )
        await conn.execute(
            "INSERT INTO cell_insar_features (cell_id, insar_velocity_mmy, insar_accel_mmy2,"
            " scatterer_count, velocita_verticale_mmy, velocita_est_mmy)"
            " VALUES ($1, -4.5, -0.3, 12, -3.9, 1.2)",
            f"{AOI}|0|0",
        )
        await conn.execute(
            "INSERT INTO susceptibility (cell_id, score, class, model_version)"
            " VALUES ($1, 0.55, 'Moderate', 'test')",
            f"{AOI}|0|0",
        )

    ctx = MonitoringContext(
        aoi_id=AOI,
        valuation_time=datetime(2026, 11, 10, tzinfo=UTC),
        cell_ids=(f"{AOI}|0|0", f"{AOI}|0|1"),
    )
    out = await StaticFactorsExecutor().run(ctx)

    con = out.static_by_cell[f"{AOI}|0|0"]
    assert con.insar_velocity_mmy == pytest.approx(-4.5)
    assert con.insar_accel_mmy2 == pytest.approx(-0.3)
    assert con.insar_scatterer_count == 12
    assert con.velocita_verticale_mmy == pytest.approx(-3.9)
    assert con.velocita_est_mmy == pytest.approx(1.2)
    assert con.susc_ispra == pytest.approx(0.55)
    # Senza scatterer la cella resta ignota, non ferma.
    senza = out.static_by_cell[f"{AOI}|0|1"]
    assert senza.insar_velocity_mmy is None
    assert senza.insar_scatterer_count is None
