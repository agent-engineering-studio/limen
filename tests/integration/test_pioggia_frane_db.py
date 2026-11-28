"""Pioggia dei pluviometri per zona franosa contro un Postgres vero (migrazione 099)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from shapely.geometry import Point

from limen.core.pioggia_frane import pioggia_prima_delle_frane, pioggia_zona_franosa
from limen.data.db import acquire
from limen.data.repos import pluviometri_repo
from limen.data.repos.landslide_events_repo import LandslideEvent, upsert_many
from limen.data.repos.pluviometri_repo import GiornoPioggia, Stazione

pytestmark = pytest.mark.integration

AOI = "it-trentino-alto-adige"
FRANOSA = f"{AOI}|0|0"
CALMA = f"{AOI}|0|1"
LONTANA = f"{AOI}|0|9"


async def _zona() -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'TAA','region',"
            "ST_Multi(ST_MakeEnvelope(11.0, 46.0, 12.0, 46.1, 4326)))",
            AOI,
        )
        celle = ((FRANOSA, 0, 11.0, 0.6), (CALMA, 1, 11.01, 0.0), (LONTANA, 9, 11.9, 0.6))
        for cid, col, x, pai in celle:
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,$2,0,$3, ST_MakeEnvelope($4,46.0,$5,46.01,4326), 1.0)",
                cid,
                AOI,
                col,
                x,
                x + 0.01,
            )
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id, pai_class_norm, distance_to_iffi_m) "
                "VALUES ($1,$2,2000)",
                cid,
                pai,
            )
        await conn.execute(
            "INSERT INTO comuni (istat_code, name, aoi_id, geom) VALUES ('022205','Trento',$1,"
            "ST_Multi(ST_MakeEnvelope(11.0, 46.0, 11.02, 46.01, 4326)))",
            AOI,
        )
        await conn.executemany(
            "INSERT INTO cell_comune (cell_id, istat_code) VALUES ($1,'022205')",
            [(FRANOSA,), (CALMA,)],
        )
    await pluviometri_repo.salva_stazioni(
        [
            Stazione(
                id="meteotrentino:T0129",
                fonte="meteotrentino",
                codice="T0129",
                nome="Trento",
                lon=11.006,
                lat=46.006,
                quota_m=312.0,
                dal=date(1990, 1, 1),
                al=None,
            )
        ]
    )
    # 5 novembre 2014: sei ore da 10 mm, dalle 06 alle 12 UTC; un buco alle 20.
    mm: list[float | None] = [0.0] * 24
    for h in range(6, 12):
        mm[h] = 10.0
    mm[19] = None
    await pluviometri_repo.sostituisci(
        "meteotrentino",
        date(2014, 11, 1),
        date(2014, 11, 30),
        [
            GiornoPioggia(
                "meteotrentino:T0129", date(2014, 11, d), tuple(mm if d == 5 else [0.0] * 24), True
            )
            for d in range(1, 8)
        ],
    )


async def test_zona_franosa_cella_e_comune(reset_db: None, pg_pool: object) -> None:
    await _zona()
    fine = datetime(2014, 11, 6, 0, tzinfo=UTC)
    r = await pioggia_zona_franosa(cell_id=FRANOSA, ore=24, fino_a=fine, raggio_km=5.0)
    assert r["copertura"] == "coperto" and r["macroregione"] == "northern_italy"
    assert r["contesto"]["franosa"] is True
    p = r["pluviometri"][0]
    assert p["id"] == "meteotrentino:T0129" and p["licenza"] == "CC BY 4.0"
    assert p["ore_misurate"] == 23 and p["validata"] is True
    assert p["cumulate"]["24h"] == {"mm": None, "ore_non_misurate": 1}
    assert p["cumulate"]["1h"] == {"mm": 0.0, "ore_non_misurate": 0}
    assert p["evento"]["cumulata_mm"] == 60.0 and p["evento"]["almeno"] is False

    # Il comune: solo le sue celle franose (la «calma» non conta).
    c = await pioggia_zona_franosa(istat_code="022205", ore=24, fino_a=fine, raggio_km=5.0)
    assert c["celle_franose"] == 1
    assert c["pluviometri"][0]["dalla_cella"] == FRANOSA

    # Nessun pluviometro entro il raggio: non coperto, mai zero.
    lontana = await pioggia_zona_franosa(cell_id=LONTANA, ore=24, fino_a=fine, raggio_km=5.0)
    assert lontana["copertura"] == "non coperto" and lontana["pluviometri"] == []

    # Un pluviometro attivo ma senza ore in archivio: non misurato, non asciutto.
    vuota = await pioggia_zona_franosa(
        cell_id=FRANOSA, ore=24, fino_a=datetime(2015, 6, 1, tzinfo=UTC), raggio_km=5.0
    )
    assert vuota["copertura"] == "non misurato"
    assert vuota["pluviometri"][0]["copertura"] == "non misurato"
    assert vuota["pluviometri"][0]["evento"] is None and "motivo_evento" in vuota["pluviometri"][0]


async def test_pioggia_prima_delle_frane(reset_db: None, pg_pool: object) -> None:
    await _zona()
    await upsert_many(
        [
            LandslideEvent(
                id="FI_1",
                source="franeitalia",
                event_time=datetime(2014, 11, 5, 0, tzinfo=UTC),
                geom=Point(11.005, 46.005),
                temporal_accuracy="T2",
            )
        ]
    )
    r = await pioggia_prima_delle_frane(
        istat_code="022205",
        dal=datetime(2014, 1, 1, tzinfo=UTC),
        ore_prima=48,
        raggio_km=5.0,
    )
    [frana] = r["frane"]
    # Datata al giorno: la finestra arriva alla fine di quel giorno, ora di Roma
    # (la mezzanotte del 6 a Roma sono le 23 UTC del 5; prima era «+24 ore»).
    assert frana["finestra"]["fine"] == datetime(2014, 11, 5, 23, tzinfo=UTC)
    assert frana["pluviometro"]["nome"] == "Trento"
    assert frana["evento"]["cumulata_mm"] == 60.0
