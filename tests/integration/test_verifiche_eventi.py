"""Il registro delle verifiche (migrazione 074), contro un Postgres vero."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from shapely.geometry import Point

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.verifiche_eventi_repo import VerificaEvento, count_by_esito, upsert

pytestmark = pytest.mark.integration

AOI = "vf-aoi"


async def _seed_comuni() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'VF','region',"
            "ST_Multi(ST_MakeEnvelope(15.0, 37.0, 16.0, 38.0, 4326)))",
            AOI,
        )
        for istat, x in (("999001", 15.0), ("999002", 15.2)):
            await conn.execute(
                "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ($1,$1,$2,"
                "ST_Multi(ST_MakeEnvelope($3, 37.0, $4, 37.2, 4326)))",
                istat,
                AOI,
                x,
                x + 0.2,
            )


_BASE = VerificaEvento(
    slug="2026-10-12-alluvione-vf",
    hazard=HazardType.FLOOD,
    esito="mancata",
    evento_at=datetime(2026, 10, 12, 15, tzinfo=UTC),
    precisione_ora="T2",
    luogo="VF",
    comuni=("999001",),
    misura={"anticipo_ore_moderato": None, "corse": []},
)


def _verifica(**kw: Any) -> VerificaEvento:
    return replace(_BASE, **kw)


async def test_senza_punto_usa_il_centroide_del_comune(reset_db: None, pg_pool: object) -> None:
    await _seed_comuni()
    luogo = await upsert(_verifica())
    assert luogo is not None
    punto, precisione = luogo
    assert punto.x == pytest.approx(15.1)
    assert precisione == "P10"


async def test_piu_comuni_valgono_p100(reset_db: None, pg_pool: object) -> None:
    await _seed_comuni()
    luogo = await upsert(_verifica(comuni=("999001", "999002")))
    assert luogo is not None
    assert luogo[1] == "P100"


async def test_un_punto_dalla_notizia_vince_sul_centroide(reset_db: None, pg_pool: object) -> None:
    await _seed_comuni()
    luogo = await upsert(_verifica(punto=Point(15.05, 37.05), precisione_luogo="P1"))
    assert luogo == (Point(15.05, 37.05), "P1")


async def test_fuori_copertura_non_ha_punto_ma_resta_nel_registro(
    reset_db: None, pg_pool: object
) -> None:
    assert await upsert(_verifica(comuni=("000000",), esito="non_verificabile")) is None
    assert await count_by_esito() == {"non_verificabile": 1}
    async with acquire() as conn:
        precisione = await conn.fetchval(
            "SELECT precisione_luogo FROM verifiche_eventi WHERE slug = $1",
            "2026-10-12-alluvione-vf",
        )
    assert precisione is None


async def test_riscrivere_aggiorna_la_stessa_riga(reset_db: None, pg_pool: object) -> None:
    await _seed_comuni()
    await upsert(_verifica())
    await upsert(_verifica(esito="contemporanea", misura={"anticipo_ore_moderato": 3}))
    assert await count_by_esito() == {"contemporanea": 1}
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT anticipo_ore_moderato, verificato_at < aggiornato_at AS aggiornata "
            "FROM verifiche_eventi"
        )
    assert row is not None
    assert row["anticipo_ore_moderato"] == 3
    assert row["aggiornata"]
