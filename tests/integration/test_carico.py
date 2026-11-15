"""Il carico di `carico.sql` gira sul database vero (#345)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.api.jobs.ids import JOB_FORECAST_HISTORY
from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos import carico_repo

pytestmark = pytest.mark.integration


async def test_il_carico_conta_i_comuni_giorno_sopra_soglia_sui_giorni_valutati(
    reset_db: None, pg_pool: object
) -> None:
    async with acquire() as conn:
        oggi = await conn.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
        ieri, l_altro_ieri = oggi - timedelta(days=1), oggi - timedelta(days=2)
        corsa = datetime.combine(l_altro_ieri, datetime.min.time(), UTC) + timedelta(hours=12)
        await conn.execute(
            "SELECT ensure_partitions('risk_assessments', $1, $2)", l_altro_ieri, oggi
        )
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ('it-prova', 'p', 'region',"
            " ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))"
        )
        for i, istat in enumerate(("099001", "099002")):
            await conn.execute(
                "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ($1, $1, 'it-prova',"
                " ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))",
                istat,
            )
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) VALUES"
                " ($1, 'it-prova', 0, $2, ST_MakeEnvelope(15, 41, 15.01, 41.01, 4326), 1)",
                f"c-{istat}",
                i,
            )
            await conn.execute(
                "INSERT INTO cell_comune (cell_id, istat_code) VALUES ($1, $2)",
                f"c-{istat}",
                istat,
            )

    async def frana() -> carico_repo.Carico | None:
        return (await carico_repo.misura(dal=None, al=None)).get(HazardType.LANDSLIDE)

    async def registra(stato: str) -> None:
        async with acquire() as conn:
            await conn.execute(
                "INSERT INTO job_runs (job_id, host, status, started_at)"
                " VALUES ($1, 'test', $2, $3)",
                JOB_FORECAST_HISTORY,
                stato,
                corsa,
            )

    try:
        # Nessuna corsa, o una fallita: niente giorni valutati, quindi nessun
        # carico — non un carico zero.
        assert await frana() is None
        await registra("error")
        assert await frana() is None

        # Una corsa riuscita l'altro ieri guarda ieri, oggi e domani; domani
        # è futuro e resta fuori. Nessuna riga = tutti sotto Moderato.
        await registra("ok")
        calmo = await frana()
        assert calmo is not None
        assert (calmo.giorni, calmo.comuni, calmo.comuni_giorno_sopra) == (2, 2, 0)
        assert (calmo.dal_giorno, calmo.al_giorno) == (ieri, oggi)
        assert calmo.quota == 0.0

        # Un comune su due previsto Moderato per ieri: 1 comune-giorno su 4.
        async with acquire() as conn:
            await conn.execute(
                "INSERT INTO risk_assessments (cell_id, hazard_type, score, class, factors,"
                " computed_at, horizon, pipeline_version) VALUES ('c-099001', 'landslide',"
                " 0.5, 'Moderate', '{}'::jsonb, $1, '+24h', 'v1-forecast+24h')",
                corsa,
            )
        carico = await frana()
        assert carico is not None
        assert carico.comuni_giorno_sopra == 1
        assert carico.quota == pytest.approx(0.25)

        # La finestra taglia: da oggi in poi, ieri non conta più.
        da_oggi = await carico_repo.misura(
            dal=datetime.combine(oggi, datetime.min.time(), UTC), al=None
        )
        assert da_oggi[HazardType.LANDSLIDE].giorni == 1
        assert da_oggi[HazardType.LANDSLIDE].comuni_giorno_sopra == 0
    finally:
        # `job_runs` non è fra le tabelle di `reset_db`.
        async with acquire() as conn:
            await conn.execute("DELETE FROM job_runs WHERE host = 'test'")
