"""Stato ricorsivo FWI contro un PostGIS reale (issue #61).

La ragione d'essere della tabella è che la ricorsione sopravviva ai riavvii.
Un test in memoria non può dimostrarlo: qui si verifica che una catena
interrotta **riprenda** invece di ripartire, e che ri-eseguire una finestra
non la biforchi.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.cli.fwi_backfill import advance_node, params_from
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.data.db import acquire
from limen.data.repos import fwi_state_repo
from limen.integrations.openmeteo.dtos import FireWeatherObservation

pytestmark = pytest.mark.integration

NODE = (16.25, 41.0)


def _params() -> object:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return params_from(t)


def _hot_days(
    first: dt.date, n: int
) -> tuple[list[dt.date], dict[dt.date, FireWeatherObservation]]:
    days = [first + dt.timedelta(days=i) for i in range(n)]
    obs = {
        d: FireWeatherObservation(
            day=d,
            temperature_c=32.0,
            relative_humidity_pct=25.0,
            wind_speed_kmh=15.0,
            rain_24h_mm=0.0,
        )
        for d in days
    }
    return days, obs


async def _write(
    days: list[dt.date],
    obs: dict[dt.date, FireWeatherObservation],
    *,
    max_gap_days: int = 5,
) -> int:
    rows = await advance_node(
        lon=NODE[0],
        lat=NODE[1],
        observations=obs,
        days=days,
        params=_params(),
        max_gap_days=max_gap_days,
    )
    return await fwi_state_repo.upsert_many(rows)


async def test_a_second_window_extends_the_chain_instead_of_restarting_it(
    reset_db: None, pg_pool: object
) -> None:
    """È l'intero motivo per cui lo stato è su disco.

    Se la seconda finestra ripartisse dai valori standard, il Drought Code
    tornerebbe a 15 e il pericolo estivo verrebbe riportato come basso nel
    momento in cui è massimo.
    """
    first_days, first_obs = _hot_days(dt.date(2026, 7, 1), 10)
    await _write(first_days, first_obs)
    after_first = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 10))
    assert after_first[0] is not None
    dc_day10 = after_first[0].dc

    second_days, second_obs = _hot_days(dt.date(2026, 7, 11), 10)
    await _write(second_days, second_obs)
    after_second = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 20))
    assert after_second[0] is not None

    # Il DC è continuato a salire da dove era, non è ripartito dal seme.
    assert after_second[0].dc > dc_day10
    # E i giorni di catena si sommano: 10 + 10.
    assert after_second[0].chain_days == 20


async def test_rerunning_a_window_does_not_fork_the_chain(reset_db: None, pg_pool: object) -> None:
    """Idempotenza: la stessa finestra due volte dà lo stesso stato.

    `latest_before` legge *strettamente prima* del primo giorno, quindi la
    seconda esecuzione riparte dallo stesso predecessore invece che da se
    stessa — che altrimenti raddoppierebbe i giorni di asciugatura.
    """
    days, obs = _hot_days(dt.date(2026, 7, 1), 10)
    assert await _write(days, obs) == 10
    once = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 10))

    assert await _write(days, obs) == 10
    twice = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 10))

    assert once[0] == twice[0]

    async with acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM fwi_state") == 10


async def test_reading_a_grid_returns_none_for_nodes_without_a_chain(
    reset_db: None, pg_pool: object
) -> None:
    """Lo sweep chiede l'intera griglia in una query: i nodi senza catena
    devono tornare `None` **nella loro posizione**, non essere saltati, o il
    mapping cella→nodo si disallineerebbe in silenzio."""
    days, obs = _hot_days(dt.date(2026, 7, 1), 3)
    await _write(days, obs)

    other = (99.0, 99.0)
    got = await fwi_state_repo.read_day([other, NODE, other], dt.date(2026, 7, 3))
    assert [g is None for g in got] == [True, False, True]


async def test_float_noise_in_a_node_coordinate_does_not_open_a_second_chain(
    reset_db: None, pg_pool: object
) -> None:
    """La griglia è costruita con un accumulatore float, quindi lo stesso nodo
    può presentarsi come 41.0 o 40.99999999999999. Senza la quantizzazione
    nella chiave sarebbero due catene, entrambe in spin-up per sempre."""
    days, obs = _hot_days(dt.date(2026, 7, 1), 3)
    await _write(days, obs)

    noisy = (NODE[0] + 1e-12, NODE[1] - 1e-12)
    got = await fwi_state_repo.read_day([noisy], dt.date(2026, 7, 3))
    assert got[0] is not None


async def test_a_chain_broken_for_too_long_restarts_instead_of_pretending(
    reset_db: None, pg_pool: object
) -> None:
    """Uno stato più vecchio del massimo scarto è una finzione.

    Portarsi un Drought Code attraverso tre settimane di meteo mancante come
    se i giorni fossero consecutivi produce un numero senza storia dietro, e
    `chain_days` continuerebbe a salire finché `spinup` dichiarerebbe
    consolidata una catena rotta. Meglio ripartire dal seme e dirlo.
    """
    first_days, first_obs = _hot_days(dt.date(2026, 7, 1), 10)
    await _write(first_days, first_obs)

    # Tre settimane dopo, ben oltre max_gap_days.
    late_days, late_obs = _hot_days(dt.date(2026, 7, 31), 5)
    await _write(late_days, late_obs)

    resumed = await fwi_state_repo.read_day([NODE], dt.date(2026, 8, 4))
    assert resumed[0] is not None
    # Catena ripartita: cinque giorni, non quindici.
    assert resumed[0].chain_days == 5
    # E il DC riparte dal seme più cinque giorni di asciugatura, non dai ~90
    # che dieci giorni di luglio avevano accumulato.
    assert resumed[0].dc < 100.0


async def test_a_short_interruption_keeps_the_chain(reset_db: None, pg_pool: object) -> None:
    """Una breve interruzione non deve buttare via settimane di siccità.

    Lo scarto massimo è ben sotto la memoria di ~52 giorni del DC proprio
    perché un fermo di due giorni non cambia il significato del codice.
    """
    first_days, first_obs = _hot_days(dt.date(2026, 7, 1), 10)
    await _write(first_days, first_obs)
    before = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 10))
    assert before[0] is not None

    gap_days, gap_obs = _hot_days(dt.date(2026, 7, 13), 3)
    await _write(gap_days, gap_obs)

    after = await fwi_state_repo.read_day([NODE], dt.date(2026, 7, 15))
    assert after[0] is not None
    assert after[0].chain_days == 13
    assert after[0].dc > before[0].dc
