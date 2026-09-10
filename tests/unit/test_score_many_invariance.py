"""`score_many` deve dare gli stessi numeri di `score`, cella per cella (#76).

È l'unico criterio che conta di questa vettorizzazione: la issue chiede
esplicitamente che i punteggi restino byte-identici. Un batch più veloce che
sposta anche solo l'ultima cifra avrebbe cambiato la scienza senza dirlo, e la
mappa mostrerebbe numeri diversi senza che nessun test se ne accorga.

Provato su tutti e tre i motori deterministici, perché il default del Protocol
è ereditato e un motore che lo sovrascrivesse male non verrebbe notato
altrimenti.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    RainfallSample,
    RainfallSeries,
    StaticFactors,
)
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.flood.engine import FloodScoringEngine
from limen.core.scoring.regional_thresholds import (
    FloodThresholds,
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire.engine import WildfireScoringEngine

NOW = dt.datetime(2026, 8, 1, 12, tzinfo=dt.UTC)


def _landslide_bundle(i: int) -> CellFeatureBundle:
    rain = RainfallSeries(
        samples=tuple(
            RainfallSample(timestamp=NOW - dt.timedelta(hours=h), precipitation_mm=0.5 + i % 3)
            for h in range(1, 25)
        )
    )
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id=f"c{i}",
        static=StaticFactors(
            cell_id=f"c{i}",
            slope_deg=10.0 + i % 30,
            iffi_density_500=float(i % 5),
            pai_class_norm=(i % 4) / 4.0,
            litho_weight=(i % 3) / 3.0,
        ),
        dynamic=DynamicInputs(valuation_time=NOW, rainfall=rain, api_30_mm=float(i % 50)),
    )


def _flood_bundle(i: int) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id=f"c{i}",
        static=StaticFactors(
            cell_id=f"c{i}",
            flood_hazard_norm=(i % 5) / 5.0,
            imperviousness_norm=(i % 7) / 7.0,
        ),
        dynamic=DynamicInputs(
            valuation_time=NOW,
            flood_forecast_rain_72h_mm=float(20 + i % 120),
            river_discharge_ratio=1.0 + (i % 30) / 10.0,
            soil_moisture_0_7=(i % 4) / 10.0,
        ),
    )


def _wildfire_bundle(i: int) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id=f"c{i}",
        static=StaticFactors(cell_id=f"c{i}", slope_deg=5.0 + i % 40, landuse_code="312"),
        dynamic=DynamicInputs(
            valuation_time=NOW,
            fire_weather=FireWeatherState(
                day=NOW.date(),
                ffmc=80.0 + i % 10,
                dmc=20.0,
                dc=200.0 + i,
                isi=5.0 + i % 8,
                bui=40.0,
                fwi=float(5 + i % 40),
                chain_days=30,
            ),
        ),
    )


def _flood_engine() -> FloodScoringEngine:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    return FloodScoringEngine(t)


def _wildfire_engine() -> WildfireScoringEngine:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return WildfireScoringEngine(t)


@pytest.mark.parametrize(
    ("engine_factory", "bundle_factory"),
    [
        (MultiFactorScoringEngine, _landslide_bundle),
        (_flood_engine, _flood_bundle),
        (_wildfire_engine, _wildfire_bundle),
    ],
    ids=["landslide", "flood", "wildfire"],
)
def test_score_many_matches_score_one_by_one(engine_factory, bundle_factory) -> None:  # type: ignore[no-untyped-def]
    engine = engine_factory()
    bundles = [bundle_factory(i) for i in range(60)]

    one_by_one = [engine.score(b) for b in bundles]
    batched = engine.score_many(bundles)

    assert len(batched) == len(one_by_one)
    for single, many in zip(one_by_one, batched, strict=True):
        assert many.score == single.score
        assert many.level is single.level
        assert many.breakdown.model_dump() == single.breakdown.model_dump()


def test_an_empty_batch_is_an_empty_list() -> None:
    assert MultiFactorScoringEngine().score_many([]) == []


@pytest.mark.parametrize(
    "engine_factory",
    [MultiFactorScoringEngine, _flood_engine, _wildfire_engine],
    ids=["landslide", "flood", "wildfire"],
)
def test_every_engine_still_satisfies_the_protocol(engine_factory) -> None:  # type: ignore[no-untyped-def]
    """Aggiungere un metodo a un Protocol `runtime_checkable` rompe
    `isinstance` per chi non lo implementa: è successo, e questo test è la
    ragione per cui i motori ora ereditano esplicitamente dal Protocol invece
    di soddisfarlo per struttura."""
    assert isinstance(engine_factory(), ScoringEngine)
