"""La catena FWI rifatta con la pioggia misurata dal DPC."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from limen.cli.fwi_backfill import params_from
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire.fwi import FwiParams, FwiState, advance
from limen.data.repos.fwi_state_repo import NodeDay
from limen.integrations.dpc import fwi_pioggia
from limen.integrations.dpc.fwi_pioggia import correggi, ricalcola

_G = date(2026, 10, 9)


def _params() -> FwiParams:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return params_from(t)


def _riga(giorno: date, *, rain: float, stato: FwiState | None = None) -> NodeDay:
    """Una giornata secca e ventosa di ottobre, come Montegiordano."""
    stato = stato or FwiState(ffmc=88.0, dmc=84.0, dc=590.0)
    uscita = advance(
        stato,
        month=giorno.month,
        temperature_c=24.0,
        relative_humidity_pct=45.0,
        wind_speed_kmh=25.0,
        rain_24h_mm=rain,
        params=_params(),
    )
    return NodeDay(
        lon=16.5,
        lat=40.0,
        day=giorno,
        outputs=uscita,
        chain_days=80,
        temperature_c=24.0,
        relative_humidity_pct=45.0,
        wind_speed_kmh=25.0,
        rain_24h_mm=rain,
    )


def _serie(n: int) -> list[NodeDay]:
    righe = [_riga(_G - timedelta(days=1), rain=0.0)]
    for i in range(n):
        righe.append(_riga(_G + timedelta(days=i), rain=0.0, stato=righe[-1].outputs.state))
    return righe


def test_la_pioggia_vera_bagna_la_catena_e_si_porta_avanti() -> None:
    serie = _serie(3)
    nuove = ricalcola(serie[1:], serie[0], {_G: 12.0}, _params())
    assert [r.rain_24h_mm for r in nuove] == [12.0, 0.0, 0.0]
    assert nuove[0].outputs.state.dmc < serie[1].outputs.state.dmc
    assert nuove[2].outputs.fwi < serie[3].outputs.fwi, "il giorno dopo parte bagnato"


def test_senza_pioggia_osservata_resta_quella_salvata() -> None:
    serie = _serie(2)
    nuove = ricalcola(serie[1:], serie[0], {_G: None}, _params())
    assert [r.outputs.fwi for r in nuove] == pytest.approx([r.outputs.fwi for r in serie[1:]])


def test_un_buco_fra_i_giorni_ferma_il_ricalcolo() -> None:
    serie = _serie(3)
    del serie[2]
    nuove = ricalcola(serie[1:], serie[0], {}, _params())
    assert [r.day for r in nuove] == [_G]


async def test_correggi_riscrive_solo_i_nodi_con_il_giorno_prima(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serie = _serie(2)
    senza_prima = [
        NodeDay(**{**{f: getattr(r, f) for f in NodeDay.__slots__}, "lon": 9.0}) for r in serie[1:]
    ]
    scritte: list[NodeDay] = []

    async def _leggi(dal: date, al: date) -> dict[tuple[float, float], list[NodeDay]]:
        return {(16.5, 40.0): serie, (9.0, 40.0): senza_prima}

    async def _scrivi(righe: list[NodeDay]) -> int:
        scritte.extend(righe)
        return len(righe)

    async def _fonte(nodi: list[tuple[float, float]], giorno: date) -> list[float | None]:
        return [15.0 if giorno == _G else None for _ in nodi]

    monkeypatch.setattr(fwi_pioggia.fwi_state_repo, "read_between", _leggi)
    monkeypatch.setattr(fwi_pioggia.fwi_state_repo, "upsert_many", _scrivi)
    conti = await correggi(dal=_G, al=_G + timedelta(days=1), params=_params(), fonte=_fonte)
    assert {(r.lon, r.day) for r in scritte} == {(16.5, _G), (16.5, _G + timedelta(days=1))}
    assert conti["righe"] == 2
    assert conti["fwi_variazione_media"] < 0


def test_il_carico_meteo_conta_le_giornate_nodo_sopra_la_fascia_alta() -> None:
    from limen.cli.backtest_wildfire import carico_meteo
    from limen.core.models.risk import FireWeatherState

    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)

    def _s(g: date, fwi: float) -> FireWeatherState:
        return FireWeatherState(
            day=g, ffmc=85.0, dmc=20.0, dc=200.0, isi=5.0, bui=30.0, fwi=fwi, chain_days=40
        )

    soglia = t.classes.high.lo * t.fwi.normalisation_max
    catene = [
        {_G: _s(_G, soglia + 1), _G + timedelta(days=1): _s(_G, 5.0)},
        {_G: _s(_G, soglia - 1), _G - timedelta(days=30): _s(_G, 60.0)},
    ]
    assert carico_meteo(catene, start=_G, end=_G + timedelta(days=1), thresholds=t) == 1 / 3
