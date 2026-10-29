"""I candidati della raccolta dalla stampa (migrazione 084, #347)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.candidati_eventi_repo import Candidato, fondi, risolvi_comuni

pytestmark = pytest.mark.integration

_BASE = Candidato(
    hazard=HazardType.LANDSLIDE,
    giorno=date(2026, 10, 28),
    parte="ignota",
    luogo="ex SS 303 a Lacedonia",
    regione="Campania",
    nomi_comuni=("Lacedonia",),
    fonti=({"testata": "Orticalab", "titolo": "Frana a Lacedonia", "url": "u1"},),
)


async def test_il_giorno_dopo_una_seconda_testata_si_unisce(
    reset_db: None, pg_pool: object
) -> None:
    primo = await fondi(_BASE)
    assert primo.testate == 1
    secondo = await fondi(
        replace(
            _BASE,
            giorno=date(2026, 10, 29),
            nomi_comuni=("lacedonia",),
            fonti=(
                {"testata": "Orticalab", "titolo": "Frana a Lacedonia", "url": "u1"},
                {"testata": "Il Mattino", "titolo": "Lacedonia, strada chiusa", "url": "u2"},
            ),
        )
    )
    assert secondo.id == primo.id
    # Il giorno resta quello della prima notizia, non del titolo uscito dopo.
    assert secondo.giorno == date(2026, 10, 28)
    assert [f["url"] for f in secondo.fonti] == ["u1", "u2"]
    assert secondo.testate == 2
    # Un altro pericolo, o un altro comune, è un altro candidato.
    assert (await fondi(replace(_BASE, hazard=HazardType.FLOOD))).id != primo.id
    assert (await fondi(replace(_BASE, nomi_comuni=("Bisaccia",)))).id != primo.id
    # Castro in un'altra regione: un omonimo, non una seconda fonte.
    assert (await fondi(replace(_BASE, regione="Lombardia"))).id != primo.id


async def test_gli_omonimi_si_sciolgono_con_la_regione(reset_db: None, pg_pool: object) -> None:
    async with acquire() as conn:
        for aoi in ("it-lombardia", "it-puglia"):
            await conn.execute(
                "INSERT INTO aoi (id, name, kind, geom) VALUES ($1, $1, 'region',"
                "ST_Multi(ST_MakeEnvelope(9, 40, 10, 41, 4326)))",
                aoi,
            )
        for istat, aoi in (("016001", "it-lombardia"), ("075001", "it-puglia")):
            await conn.execute(
                "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ($1, 'Castro', $2,"
                "ST_Multi(ST_MakeEnvelope(9, 40, 9.1, 40.1, 4326)))",
                istat,
                aoi,
            )
    assert await risolvi_comuni(("Castro",), "Puglia") == ["075001"]
    assert await risolvi_comuni(("castro",), None) == []
    assert await risolvi_comuni(("Castro", "Nessuno"), "Puglia") == []
