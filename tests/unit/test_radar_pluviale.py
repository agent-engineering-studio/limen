"""Gli usi del radar nel ramo pluviale dell'alluvione (#643): spenti finché non sono misurati.

Spenti, il punteggio è identico a prima; accesi da YAML, ognuno fa una cosa sola.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import pytest
import rasterio
from dpc_radar import product
from rasterio.crs import CRS

from limen.agents.executors.observed_rain import ObservedRainExecutor
from limen.core.features.assembler import assemble_bundles
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.core.models.risk import CellFeatureBundle, DynamicInputs, StaticFactors
from limen.core.scoring.flood import FloodScoringEngine
from limen.core.scoring.flood.trigger import rarity_trigger
from limen.core.scoring.regional_thresholds import (
    FloodThresholds,
    NowcastBlock,
    RadarCiecoBlock,
    RaritaBlock,
    load_hazard_thresholds,
)
from limen.integrations.dpc import RainGrid, osservata

_T = dt.datetime(2026, 10, 10, 6, tzinfo=dt.UTC)


def _soglie(**observed: Any) -> FloodThresholds:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    assert t.pluvial.observed is not None
    oss = t.pluvial.observed.model_copy(update=observed)
    return t.model_copy(update={"pluvial": t.pluvial.model_copy(update={"observed": oss})})


def _bundle(**dyn: Any) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="it-calabria",
        cell_id="c",
        static=StaticFactors(cell_id="c", flood_hazard_norm=0.8),
        dynamic=DynamicInputs(valuation_time=_T, soil_moisture_0_7=0.35, **dyn),
    )


def test_spenti_il_punteggio_non_cambia() -> None:
    base = {
        "flood_forecast_rain_72h_mm": 30.0,
        "flood_rain_observed_mm": 20.0,
        "flood_rain_head_mm": 5.0,
    }
    prima = FloodScoringEngine(_soglie()).score(_bundle(**base))
    con_dati = FloodScoringEngine(_soglie()).score(_bundle(**base, flood_rain_observed_years=40.0))
    assert con_dati.score == prima.score
    assert con_dati.breakdown.rain_observed_years == 40.0


def test_la_rarita_alza_il_ramo_pluviale_in_scala_logaritmica() -> None:
    r = RaritaBlock(from_years=2, full_years=20)
    assert rarity_trigger(2.0, r) == 0.0
    assert rarity_trigger(20.0, r) == 1.0
    assert rarity_trigger(50.0, r) == 1.0
    assert rarity_trigger(2.0 * 10**0.5, r) == pytest.approx(0.5)
    motore = FloodScoringEngine(_soglie(rarity=r))
    poca = {"flood_forecast_rain_72h_mm": 10.0, "flood_rain_observed_mm": 10.0}
    assert motore.score(_bundle(**poca)).breakdown.pluvial == 0.0
    rara = motore.score(_bundle(**poca, flood_rain_observed_years=20.0))
    assert rara.breakdown.pluvial == 1.0
    assert rara.score == pytest.approx(0.8)


def test_il_nowcast_sostituisce_il_resto_solo_quando_e_maggiore() -> None:
    motore = FloodScoringEngine(_soglie(nowcast=NowcastBlock(minutes=60, max_age_minutes=15)))
    a = {
        "flood_forecast_rain_72h_mm": 20.0,
        "flood_rain_observed_mm": 100.0,
        "flood_rain_head_mm": 8.0,
    }
    assert motore.score(_bundle(**a)).breakdown.rain_mm == 108.0
    assert motore.score(_bundle(**a, flood_rain_ahead_mm=30.0)).breakdown.rain_mm == 130.0
    assert motore.score(_bundle(**a, flood_rain_ahead_mm=2.0)).breakdown.rain_mm == 108.0
    # Spento nello YAML, il motore non lo legge nemmeno se il dato c'è.
    spento = FloodScoringEngine(_soglie()).score(_bundle(**a, flood_rain_ahead_mm=30.0))
    assert spento.breakdown.rain_mm == 108.0


def test_lo_yaml_rifiuta_una_rampa_al_contrario() -> None:
    with pytest.raises(ValueError, match="full_years"):
        RaritaBlock(from_years=20, full_years=5)
    with pytest.raises(ValueError):
        NowcastBlock(minutes=180, max_age_minutes=15)
    from limen.core.scoring.regional_thresholds import PluvialObservedBlock

    with pytest.raises(ValueError, match="hours in 3, 6 or 24"):
        PluvialObservedBlock(
            hours=12,
            max_age_minutes=90,
            max_step_mm=150,
            rarity=RaritaBlock(from_years=2, full_years=20),
        )


def test_spenti_i_factors_restano_quelli_di_prima() -> None:
    r = FloodScoringEngine(_soglie()).score(_bundle(flood_forecast_rain_72h_mm=30.0))
    payload = r.breakdown.factors_payload()
    assert "rain_observed_years" not in payload and "rain_ahead_mm" not in payload


def _frame(valore: float) -> RainGrid:
    return RainGrid(
        product("CUM24"),
        _T - dt.timedelta(minutes=20),
        np.full((10, 10), valore),
        rasterio.Affine(0.1, 0, 15.0, 0, -0.1, 42.0),
        CRS.from_epsg(4326),
    )


def _ctx() -> MonitoringContext:
    return MonitoringContext(
        aoi_id="aoi",
        hazard_type=HazardType.FLOOD,
        valuation_time=_T,
        cell_ids=("a", "b"),
        cell_centroids={"a": (15.25, 41.75), "b": (15.75, 41.25)},
    )


def _passo(valore: float, **kw: Any) -> ObservedRainExecutor:
    async def _fetch(_h: int) -> RainGrid:
        return _frame(valore)

    async def _uguale(_h: int, _at: dt.datetime) -> RainGrid:
        return _frame(valore)

    return ObservedRainExecutor(
        hours=24, max_age_minutes=90, max_step_mm=150.0, fetch=_fetch, fetch_at=_uguale, **kw
    )


async def test_dove_il_radar_e_cieco_uno_zero_non_e_asciutto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(osservata, "affidabilita", lambda _g, _p: [0.2, 0.9])
    cieco = RadarCiecoBlock(min_reliability=0.5, dry_mm=1.0)
    out = await _passo(0.0, blind=cieco).run(_ctx())
    assert out.flood_rain_observed_by_cell == {"b": 0.0}
    piove = await _passo(40.0, blind=cieco).run(_ctx())
    assert piove.flood_rain_observed_by_cell == {"a": 40.0, "b": 40.0}


async def test_rarita_e_nowcast_arrivano_alle_celle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(osservata, "ritorno", lambda _g, _p: [12.0, None])

    async def _nowcast(minuti: int, punti: Any, **_kw: Any) -> list[float | None]:
        assert minuti == 60
        return [5.0, 0.0]

    monkeypatch.setattr(osservata, "nowcast", _nowcast)
    nowcast = NowcastBlock(minutes=60, max_age_minutes=15)
    out = await _passo(30.0, rarity=True, nowcast=nowcast).run(_ctx())
    assert out.flood_rain_observed_years_by_cell == {"a": 12.0}
    assert out.flood_rain_ahead_by_cell == {"a": 5.0, "b": 0.0}
    dyn = {b.cell_id: b.dynamic for b in assemble_bundles(out)}
    assert (dyn["a"].flood_rain_observed_years, dyn["a"].flood_rain_ahead_mm) == (12.0, 5.0)


async def test_spenti_il_passo_non_chiede_niente_al_radar(monkeypatch: pytest.MonkeyPatch) -> None:
    def vietato(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("spento: non doveva chiedere")

    for nome in ("affidabilita", "ritorno", "nowcast"):
        monkeypatch.setattr(osservata, nome, vietato)
    out = await _passo(30.0).run(_ctx())
    assert out.flood_rain_ahead_by_cell == {} and out.flood_rain_observed_years_by_cell == {}


def test_le_letture_vere_della_libreria_sulla_griglia() -> None:
    from dataclasses import replace

    g = replace(_frame(180.0), transform=rasterio.Affine(0.1, 0, 15.0, 0, -0.1, 39.0))
    [anni] = osservata.ritorno(g, [(15.75, 38.05)])
    assert anni is not None and anni >= 20
    [a] = osservata.affidabilita(g, [(15.75, 38.05)])
    assert a is not None and 0.0 <= a <= 1.0
