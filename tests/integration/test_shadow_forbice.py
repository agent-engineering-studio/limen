"""La forbice dello sfidante in ombra, letta da ``model_runs`` (#484)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.model_runs_repo import ModelRunRow, insert_many
from limen.ml.shadow import collect_shadow_summary

pytestmark = pytest.mark.integration


async def test_una_forbice_per_versione_e_nulla_senza_conformal(
    reset_db: None, pg_pool: object
) -> None:
    ora = datetime.now(UTC) - timedelta(hours=1)
    async with acquire() as conn:
        await conn.execute("SELECT ensure_partitions('model_runs', 3)")
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ('it-prova', 'Prova', 'region',"
            " ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))"
        )
        await conn.execute(
            "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) VALUES"
            " ('c-prova', 'it-prova', 0, 0, ST_MakeEnvelope(15, 41, 15.01, 41.01, 4326), 1)"
        )

    def riga(versione: str, breakdown: dict[str, object]) -> ModelRunRow:
        return ModelRunRow(
            cell_id="c-prova",
            valuation_time=ora,
            aoi_id="it-prova",
            model_uri=f"models:/frane/{versione}",
            model_version=versione,
            role="challenger",
            probability=0.2,
            risk_class="Low",
            breakdown=breakdown,
            hazard_type=HazardType.LANDSLIDE,
        )

    await insert_many([riga("4", {"conformal_q90": 0.12}), riga("3", {})])
    async with acquire() as conn:
        sintesi = await collect_shadow_summary(conn, since=ora - timedelta(days=1), aoi_filter=None)
    assert sintesi.model_versions == ["3", "4"]
    assert sintesi.forbice_q90 == {"3": None, "4": 0.12}
