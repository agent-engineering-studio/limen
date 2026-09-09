"""Dati di addestramento del challenger incendio (issue #68).

Le proprietà che vivono nel database, e che un errore renderebbe invisibile
finché il modello non sembra bravo per il motivo sbagliato:

* **niente leakage temporale** — la memoria del fuoco di un campione conta
  solo i giorni *precedenti*. Con la densità completa lo SHAP dava a quella
  feature un'importanza di 3,32 contro 0,29 del FWI: il modello leggeva in
  gran parte la propria etichetta;
* le pseudo-assenze portano un **tempo** e non cadono su giorni di fuoco;
* il filtro che tiene fuori i campioni senza meteo ricostruito, perché per il
  FWI zero non è un valore neutro.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.core.models.hazard import HazardType
from limen.data.db import acquire
from limen.data.repos.training_samples_repo import (
    TrainingSample,
    fetch_samples,
    fetch_wildfire_ready_samples,
    insert_many,
)
from limen.ml.feature_store import _fire_days_before, extract_training_samples

pytestmark = pytest.mark.integration

AOI = "bt-wf-train"
SEASON = (dt.datetime(2024, 7, 1, tzinfo=dt.UTC), dt.datetime(2024, 8, 31, tzinfo=dt.UTC))


async def _seed(cells: int = 4) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT wf','region',"
            "ST_Multi(ST_MakeEnvelope(16.0, 40.9, 16.5, 41.2, 4326)))",
            AOI,
        )
        for i in range(cells):
            x = 16.0 + i * 0.1
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,$2,0,$3, ST_MakeEnvelope($4,41.0,$5,41.05,4326), 1.0)",
                f"{AOI}|0|{i}",
                AOI,
                i,
                x,
                x + 0.1,
            )
            await conn.execute(
                "INSERT INTO cell_static_factors (cell_id, slope_deg, landuse_code, "
                "wui_proximity_norm, fire_density) VALUES ($1, 12.0, '312', 0.3, 0)",
                f"{AOI}|0|{i}",
            )


async def _fire_day(cell_index: int, day: dt.date) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO fire_events (cell_id, event_date, hotspots, sources) "
            "VALUES ($1,$2,3,ARRAY['VIIRS_SNPP_SP'])",
            f"{AOI}|0|{cell_index}",
            day,
        )


async def test_fire_memory_excludes_the_sample_own_day(reset_db: None, pg_pool: object) -> None:
    """Il leakage temporale, in una riga.

    La cella ha bruciato tre volte; un campione del secondo giorno deve vedere
    **uno** solo — quello prima. Contare anche il proprio insegnerebbe al
    modello a leggere l'etichetta.
    """
    await _seed()
    days = [dt.date(2024, 7, 10), dt.date(2024, 7, 20), dt.date(2024, 8, 5)]
    for day in days:
        await _fire_day(0, day)

    before_first = await _fire_days_before(
        f"{AOI}|0|0", before=dt.datetime(2024, 7, 10, 12, tzinfo=dt.UTC)
    )
    before_second = await _fire_days_before(
        f"{AOI}|0|0", before=dt.datetime(2024, 7, 20, 12, tzinfo=dt.UTC)
    )
    before_third = await _fire_days_before(
        f"{AOI}|0|0", before=dt.datetime(2024, 8, 5, 12, tzinfo=dt.UTC)
    )

    assert (before_first, before_second, before_third) == (0, 1, 2)


async def test_extraction_writes_past_only_fire_memory(reset_db: None, pg_pool: object) -> None:
    await _seed()
    await _fire_day(0, dt.date(2024, 7, 10))
    await _fire_day(0, dt.date(2024, 7, 20))

    await extract_training_samples(
        hazard=HazardType.WILDFIRE,
        min_occurrence=SEASON[0],
        max_occurrence=SEASON[1],
    )

    samples = await fetch_samples(hazard=HazardType.WILDFIRE)
    positives = sorted((s for s in samples if s.label == 1), key=lambda s: s.valuation_time)
    assert [s.features["fire"]["density_hist"] for s in positives] == [0.0, 1.0]


async def test_every_fire_day_is_its_own_positive(reset_db: None, pg_pool: object) -> None:
    """Tre giorni di fuoco sono tre giornate in cui la cella era in pericolo."""
    await _seed()
    for day in (dt.date(2024, 7, 10), dt.date(2024, 7, 11), dt.date(2024, 7, 12)):
        await _fire_day(0, day)

    await extract_training_samples(
        hazard=HazardType.WILDFIRE, min_occurrence=SEASON[0], max_occurrence=SEASON[1]
    )

    samples = await fetch_samples(hazard=HazardType.WILDFIRE)
    assert sum(1 for s in samples if s.label == 1) == 3


async def test_positives_are_anchored_at_noon(reset_db: None, pg_pool: object) -> None:
    """Il FWI di Van Wagner è definito sulle condizioni di mezzogiorno:
    ancorare a mezzanotte chiederebbe alla catena l'indice del giorno
    sbagliato al confine."""
    await _seed()
    await _fire_day(0, dt.date(2024, 7, 10))

    await extract_training_samples(
        hazard=HazardType.WILDFIRE, min_occurrence=SEASON[0], max_occurrence=SEASON[1]
    )

    positives = [s for s in await fetch_samples(hazard=HazardType.WILDFIRE) if s.label == 1]
    assert positives[0].valuation_time.hour == 12


async def test_controls_carry_a_time_and_avoid_fire_days(reset_db: None, pg_pool: object) -> None:
    """Il predittore dominante è il meteo del giorno: una negativa senza un
    giorno credibile non insegnerebbe nulla, e una che cade su un giorno di
    fuoco è un positivo etichettato negativo."""
    await _seed()
    fire_days = {dt.date(2024, 7, 10), dt.date(2024, 7, 11)}
    for day in fire_days:
        await _fire_day(0, day)

    await extract_training_samples(
        hazard=HazardType.WILDFIRE, min_occurrence=SEASON[0], max_occurrence=SEASON[1]
    )

    samples = await fetch_samples(hazard=HazardType.WILDFIRE)
    controls = [s for s in samples if s.label == 0]
    assert controls, "servono pseudo-assenze"
    assert all(s.valuation_time.hour == 12 for s in controls)
    burnt_controls = [s for s in controls if s.cell_id == f"{AOI}|0|0"]
    assert all(s.valuation_time.date() not in fire_days for s in burnt_controls)


async def test_only_enriched_samples_reach_the_training_set(
    reset_db: None, pg_pool: object
) -> None:
    """Per il FWI zero non è neutro: un positivo non arricchito insegnerebbe
    che si brucia con pericolo nullo."""
    await _seed()
    await insert_many(
        [
            TrainingSample(
                cell_id=f"{AOI}|0|0",
                valuation_time=dt.datetime(2024, 7, 10, 12, tzinfo=dt.UTC),
                label=1,
                label_source="firms",
                features={"fire": {"fuel_class_norm": 0.6}},
                split_block="b1",
                hazard_type=HazardType.WILDFIRE,
            ),
            TrainingSample(
                cell_id=f"{AOI}|0|1",
                valuation_time=dt.datetime(2024, 7, 11, 12, tzinfo=dt.UTC),
                label=1,
                label_source="firms",
                features={"fire": {"fuel_class_norm": 0.6, "fwi": 35.0}},
                split_block="b1",
                hazard_type=HazardType.WILDFIRE,
            ),
        ]
    )

    ready = await fetch_wildfire_ready_samples()

    assert [s.cell_id for s in ready] == [f"{AOI}|0|1"]
