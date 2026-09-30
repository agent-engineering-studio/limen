"""Il passo FWI non ripaga la stessa giornata ventiquattro volte (#142).

La catena avanza di giorno, lo sweep gira di ora. Finché il passo rileggeva
la griglia a ogni tick, Open-Meteo veniva interrogato su 1446 nodi per quattro
variabili per sette giorni, ventiquattro volte al giorno: il tetto giornaliero
gratuito è saltato e *ogni* cella si è ritrovata senza catena, cioè con
`fire_weather: null` e punteggio zero. Questi test fissano le due regole che
lo evitano — leggere il giorno già scritto, e chiedere solo i giorni mancanti.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from limen.agents.executors.fwi_update import FwiUpdateExecutor
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import FireWeatherState
from limen.core.scoring.wildfire.fwi import FwiState
from limen.data.repos import fwi_state_repo
from limen.data.repos.fwi_state_repo import StoredChain

BBOX = (16.0, 40.0, 16.5, 40.5)
GIORNO = date(2026, 7, 10)


def _stato(day: date) -> FireWeatherState:
    return FireWeatherState(
        day=day, ffmc=85.0, dmc=6.0, dc=15.0, isi=1.0, bui=5.0, fwi=3.0, chain_days=40
    )


class _ClienteCheAccusa:
    """Ogni chiamata è un errore: qui la rete non deve essere toccata."""

    def __init__(self) -> None:
        self.chiamate: list[list[date]] = []

    async def get_fire_weather_grid(self, **kwargs: object) -> list[list[object]]:
        inizio = kwargs["window_start"]
        fine = kwargs["window_end"]
        assert isinstance(inizio, datetime) and isinstance(fine, datetime)
        giorni = [
            inizio.date() + timedelta(days=i) for i in range((fine.date() - inizio.date()).days + 1)
        ]
        self.chiamate.append(giorni)
        nodi = kwargs["nodes"]
        assert isinstance(nodi, list)
        return [[] for _ in nodi]


@pytest.mark.asyncio
async def test_il_giorno_gia_scritto_non_si_riscarica(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _ClienteCheAccusa()
    exe = FwiUpdateExecutor(client=cliente)  # type: ignore[arg-type]

    async def _read_day(nodes: list[tuple[float, float]], day: date) -> list[FireWeatherState]:
        assert day == GIORNO
        return [_stato(day) for _ in nodes]

    monkeypatch.setattr(fwi_state_repo, "read_day", _read_day)
    ctx = MonitoringContext(
        aoi_id="it-basilicata",
        valuation_time=datetime.combine(GIORNO, datetime.min.time(), UTC),
        bbox=BBOX,
    )

    out = await exe.run(ctx)

    assert cliente.chiamate == []
    assert out.fwi_nodes
    assert all(s is not None for s in out.fwi_by_node)


@pytest.mark.asyncio
async def test_si_chiedono_solo_i_giorni_mancanti(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _ClienteCheAccusa()
    exe = FwiUpdateExecutor(client=cliente)  # type: ignore[arg-type]

    async def _read_day(nodes: list[tuple[float, float]], day: date) -> list[None]:
        return [None for _ in nodes]

    async def _latest_before(lon: float, lat: float, day: date) -> StoredChain:
        return StoredChain(
            day=day - timedelta(days=1),
            state=FwiState(ffmc=85.0, dmc=6.0, dc=15.0),
            chain_days=40,
        )

    monkeypatch.setattr(fwi_state_repo, "read_day", _read_day)
    monkeypatch.setattr(fwi_state_repo, "latest_before", _latest_before)
    ctx = MonitoringContext(
        aoi_id="it-basilicata",
        valuation_time=datetime.combine(GIORNO, datetime.min.time(), UTC),
        bbox=BBOX,
    )

    await exe.run(ctx)

    assert len(cliente.chiamate) == 1
    # Il giorno da camminare più quello prima, che porta la pioggia delle 24 h
    # del primo mezzogiorno. Non i sei di `max_gap_days`.
    assert cliente.chiamate[0] == [GIORNO - timedelta(days=1), GIORNO]


@pytest.mark.asyncio
async def test_un_nodo_freddo_allarga_la_finestra(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente = _ClienteCheAccusa()
    exe = FwiUpdateExecutor(client=cliente)  # type: ignore[arg-type]

    async def _read_day(nodes: list[tuple[float, float]], day: date) -> list[None]:
        return [None for _ in nodes]

    async def _latest_before(lon: float, lat: float, day: date) -> None:
        return None

    monkeypatch.setattr(fwi_state_repo, "read_day", _read_day)
    monkeypatch.setattr(fwi_state_repo, "latest_before", _latest_before)
    ctx = MonitoringContext(
        aoi_id="it-basilicata",
        valuation_time=datetime.combine(GIORNO, datetime.min.time(), UTC),
        bbox=BBOX,
    )

    await exe.run(ctx)

    gap = exe._t.fwi.max_gap_days
    assert cliente.chiamate[0][0] == GIORNO - timedelta(days=gap + 1)
    assert cliente.chiamate[0][-1] == GIORNO
