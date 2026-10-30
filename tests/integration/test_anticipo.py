"""La misura di `anticipo.sql` gira sul database vero (#347)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos import anticipo_repo

pytestmark = pytest.mark.integration


async def test_la_misura_dice_da_quando_ci_sono_le_partizioni(
    reset_db: None, pg_pool: object
) -> None:
    async with acquire() as conn:
        await conn.execute("SELECT ensure_partitions('risk_assessments', 3)")
        oggi = await conn.fetchval("SELECT (now() AT TIME ZONE 'UTC')::date")
    misura = await anticipo_repo.misura(
        comuni=["000000"],
        hazard=HazardType.LANDSLIDE,
        evento_at=datetime.now(UTC) - timedelta(hours=1),
        tolleranza_ore=12,
    )
    assert misura["celle"] == 0
    assert date.fromisoformat(misura["partizioni_dal"]) <= oggi


async def test_il_pericolo_e_valutato_se_ha_girato_la_regione_dell_evento(
    reset_db: None, pg_pool: object
) -> None:
    from limen.api.jobs.ids import JOB_HOURLY_MONITORING

    evento = datetime.now(UTC) - timedelta(hours=2)
    async with acquire() as conn:
        await conn.execute("SELECT ensure_partitions('risk_assessments', 3)")
        for aoi in ("it-prova", "it-altra"):
            await conn.execute(
                "INSERT INTO aoi (id, name, kind, geom) VALUES ($1, $1, 'region',"
                " ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))",
                aoi,
            )
        await conn.execute(
            "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ('099001', 'Prova',"
            " 'it-prova', ST_Multi(ST_MakeEnvelope(15, 41, 15.1, 41.1, 4326)))"
        )
        await conn.execute(
            "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) VALUES"
            " ('c-prova', 'it-prova', 0, 0, ST_MakeEnvelope(15, 41, 15.01, 41.01, 4326), 1)"
        )
        await conn.execute(
            "INSERT INTO cell_comune (cell_id, istat_code) VALUES ('c-prova', '099001')"
        )

    async def valutato() -> tuple[bool, bool]:
        m = await anticipo_repo.misura(
            comuni=["099001"], hazard=HazardType.LANDSLIDE, evento_at=evento, tolleranza_ore=12
        )
        return bool(m["pericolo_valutato"]), bool(m["fondo_valutato"])

    async def corsa(scope: str, stato: str, prima: timedelta = timedelta(hours=5)) -> None:
        async with acquire() as conn:
            await conn.execute(
                "INSERT INTO job_runs (job_id, scope, host, status, started_at, metrics)"
                " VALUES ($1, $2, 'test', $3, $4, '{\"hazard\": \"landslide\"}')",
                JOB_HOURLY_MONITORING,
                scope,
                stato,
                evento - prima,
            )

    assert await valutato() == (False, False)
    # Un'altra regione che gira non copre questa; una corsa fallita neppure.
    await corsa("it-altra", "ok")
    await corsa("it-prova", "error")
    assert await valutato() == (False, False)
    # La sua regione è girata, anche se lo sweep calmo non ha scritto righe.
    await corsa("it-prova", "ok")
    try:
        # Girata nelle ore prima ma non nei giorni del fondo: un pericolo
        # appena acceso non ha fondo, e non lo si legge come fondo basso.
        assert await valutato() == (True, False)
        await corsa("it-prova", "ok", prima=timedelta(days=6))
        assert await valutato() == (True, True)
    finally:
        # `job_runs` non è fra le tabelle di `reset_db`.
        async with acquire() as conn:
            await conn.execute("DELETE FROM job_runs WHERE host = 'test'")
