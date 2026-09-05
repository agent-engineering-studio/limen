"""Backtest incendio contro perimetri di area bruciata (issue #62).

L'endpoint pubblico EFFIS risponde 403 senza accreditamento, quindi la
verifica non può passare da una fetch reale. Il ground truth qui è
sintetico e inserito in `fire_perimeters`: è la stessa tabella che l'ingest
popola, quindi ciò che si prova è esattamente la logica che girerà sui dati
veri — la selezione delle celle bruciate, il conteggio di hit/mancati e il
preavviso.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.cli.backtest_wildfire import evaluate, fetch_burnt_cells, replay_chain
from limen.core.models.hazard import HazardType
from limen.core.models.risk import FireWeatherState, RiskLevel, StaticFactors
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.data.db import acquire

pytestmark = pytest.mark.integration

AOI = "bt-fire"
NODE = (16.25, 41.0)


def _thresholds() -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t


async def _seed(fire_dates: dict[str, dt.date]) -> None:
    """Un'AOI con una cella per incendio, ognuna dentro il suo perimetro."""
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO aoi (id, name, kind, geom) VALUES ($1,'BT fire','region',"
            "ST_Multi(ST_MakeEnvelope(16.0, 40.8, 16.6, 41.3, 4326)))",
            AOI,
        )
        for i, (cell_id, fire_date) in enumerate(sorted(fire_dates.items())):
            x = 16.1 + i * 0.05
            await conn.execute(
                "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
                "VALUES ($1,$2,0,$3, ST_MakeEnvelope($4,41.0,$5,41.01,4326), 1.0)",
                cell_id,
                AOI,
                i,
                x,
                x + 0.01,
            )
            await conn.execute(
                "INSERT INTO fire_perimeters (id, fire_date, geom) VALUES ($1,$2,"
                "ST_Multi(ST_MakeEnvelope($3,40.99,$4,41.02,4326)))",
                f"perim-{i}",
                fire_date,
                x - 0.005,
                x + 0.015,
            )


async def test_only_cells_inside_a_perimeter_are_truth(reset_db: None, pg_pool: object) -> None:
    """Il ground truth è l'intersezione geometrica, non l'AOI intera."""
    await _seed({f"{AOI}|0|0": dt.date(2026, 8, 10)})
    async with acquire() as conn:
        # Una cella lontana dai perimetri: non deve entrare nel truth set.
        await conn.execute(
            "INSERT INTO grid_cells (id, aoi_id, row_idx, col_idx, geom, area_km2) "
            "VALUES ($1,$2,9,9, ST_MakeEnvelope(16.5,41.2,16.51,41.21,4326), 1.0)",
            f"{AOI}|9|9",
            AOI,
        )
    truth = await fetch_burnt_cells(AOI, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
    assert set(truth) == {f"{AOI}|0|0"}


async def test_a_cell_that_burned_twice_counts_once(reset_db: None, pg_pool: object) -> None:
    """Altrimenti un'area ben allertata gonfierebbe l'hit rate quante volte
    ha preso fuoco."""
    cell = f"{AOI}|0|0"
    await _seed({cell: dt.date(2026, 8, 10)})
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO fire_perimeters (id, fire_date, geom) VALUES ('perim-again',"
            "$1, ST_Multi(ST_MakeEnvelope(16.095,40.99,16.115,41.02,4326)))",
            dt.date(2026, 9, 1),
        )
    truth = await fetch_burnt_cells(AOI, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
    assert list(truth) == [cell]
    # L'ancora è il *primo* incendio: usare l'ultimo darebbe un preavviso
    # calcolato su un evento che l'allerta non poteva anticipare.
    assert truth[cell][0] == dt.date(2026, 8, 10)


def _chain(
    days: list[dt.date], fwi_by_day: dict[dt.date, float]
) -> dict[dt.date, FireWeatherState]:
    return {
        d: FireWeatherState(
            day=d,
            ffmc=95.0,
            dmc=150.0,
            dc=500.0,
            isi=15.0,
            bui=150.0,
            fwi=fwi_by_day.get(d, 2.0),
            chain_days=90,
        )
        for d in days
    }


async def test_only_the_lead_horizon_counts(reset_db: None, pg_pool: object) -> None:
    """La domanda dell'issue è sulle 72 h prima dell'innesco, non sulla
    stagione.

    Scandire l'intera finestra prenderebbe la prima allerta dell'estate: con
    la finestra di default (400 giorni) ogni incendio risulterebbe allertato
    un anno prima, e il report direbbe 0% di hit rate qualunque sia la bravura
    del modello. Qui il pericolo è estremo **solo** sette giorni prima e mite
    nei tre che contano.
    """
    cell = f"{AOI}|0|0"
    fire = dt.date(2026, 8, 10)
    await _seed({cell: fire})
    truth = await fetch_burnt_cells(AOI, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
    days = [fire - dt.timedelta(days=d) for d in range(10, -1, -1)]

    far_back = _chain(days, {fire - dt.timedelta(days=7): 48.0})
    m = evaluate(
        aoi_id=AOI,
        truth=truth,
        static={cell: StaticFactors(cell_id=cell, landuse_code="312", slope_deg=30.0)},
        nodes=[NODE],
        chains=[far_back],
        days=days,
        thresholds=_thresholds(),
        alert_level=RiskLevel.High,
    )
    assert m.hits == 0
    assert m.misses == 1


async def test_a_warning_inside_the_horizon_is_a_hit_with_its_lead(
    reset_db: None, pg_pool: object
) -> None:
    """Il preavviso è la distanza fra la prima allerta *dentro* l'orizzonte e
    l'incendio, e si prende la più lontana delle due utili: due giorni di
    anticipo valgono più di zero."""
    cell = f"{AOI}|0|0"
    fire = dt.date(2026, 8, 10)
    await _seed({cell: fire})
    truth = await fetch_burnt_cells(AOI, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))
    days = [fire - dt.timedelta(days=d) for d in range(10, -1, -1)]

    # Estremo da due giorni prima in poi: la prima allerta utile è a 48 h.
    hot = _chain(
        days,
        {
            fire - dt.timedelta(days=2): 48.0,
            fire - dt.timedelta(days=1): 48.0,
            fire: 48.0,
        },
    )
    m = evaluate(
        aoi_id=AOI,
        truth=truth,
        static={cell: StaticFactors(cell_id=cell, landuse_code="312", slope_deg=30.0)},
        nodes=[NODE],
        chains=[hot],
        days=days,
        thresholds=_thresholds(),
        alert_level=RiskLevel.High,
    )
    assert m.hits == 1
    assert m.hit_rate == 1.0
    assert m.mean_lead_hours == pytest.approx(48.0)
    # Il FAR non è misurato da questo replay e non deve fingere di esserlo.
    assert m.false_alarms == 0


async def test_a_cell_never_reaching_the_level_is_a_miss(reset_db: None, pg_pool: object) -> None:
    """Una catena mite non deve produrre allerte, e l'incendio resta mancato:
    è il caso che tiene onesto l'hit rate."""
    cell = f"{AOI}|0|0"
    fire = dt.date(2026, 8, 10)
    await _seed({cell: fire})
    truth = await fetch_burnt_cells(AOI, start=dt.date(2026, 1, 1), end=dt.date(2026, 12, 31))

    days = [fire - dt.timedelta(days=d) for d in range(3, 0, -1)]
    mild = {
        d: FireWeatherState(
            day=d, ffmc=70.0, dmc=10.0, dc=50.0, isi=1.0, bui=12.0, fwi=2.0, chain_days=90
        )
        for d in days
    }
    m = evaluate(
        aoi_id=AOI,
        truth=truth,
        static={cell: StaticFactors(cell_id=cell, landuse_code="312", slope_deg=30.0)},
        nodes=[NODE],
        chains=[mild],
        days=days,
        thresholds=_thresholds(),
        alert_level=RiskLevel.High,
    )
    assert m.hits == 0
    assert m.misses == 1
    assert m.cells_warned == 0
    assert m.hit_rate == 0.0


def test_the_replay_starts_from_the_seed_not_from_operational_state() -> None:
    """Un backtest che leggesse `fwi_state` rigiocherebbe l'estate scorsa
    partendo dal Drought Code di oggi: il risultato sarebbe una previsione
    che conosce il futuro."""
    from limen.integrations.openmeteo.dtos import MeteoSnapshot, WeatherSample

    t = _thresholds()
    days = [dt.date(2026, 7, 1) + dt.timedelta(days=i) for i in range(3)]
    samples = [
        WeatherSample(
            timestamp=dt.datetime.combine(d, dt.time(12), dt.UTC),
            precipitation_mm=0.0,
            temperature_c=30.0,
            relative_humidity_pct=30.0,
            wind_speed_kmh=12.0,
        )
        for d in days
    ]
    snapshot = MeteoSnapshot(
        centroid_lon=NODE[0],
        centroid_lat=NODE[1],
        window_start=samples[0].timestamp,
        window_end=samples[-1].timestamp,
        samples=samples,
    )
    chain = replay_chain(snapshot=snapshot, days=days, thresholds=t)
    assert [c.chain_days for c in chain.values()] == [1, 2, 3]
    # Il DC parte dal seme e sale di qualche unità al giorno, non dai
    # ~400 che la catena operativa porta a settembre.
    assert chain[days[0]].dc < t.fwi.dc_start + 12.0
