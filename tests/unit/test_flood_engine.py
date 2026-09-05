"""Motore alluvione e i suoi due trigger (issue #63).

Il pericolo che il progetto aveva già in casa: il mosaico idraulico ISPRA
alimentava il componente H del motore frane da tempo, e qui diventa la
suscettibilità di un pericolo suo.

Quel che si verifica è la forma della combinazione — massimo e non somma,
prodotto e non addizione — perché è lì che stanno le decisioni di progetto
che una "semplificazione" futura romperebbe in silenzio.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.config.settings import ScoringEngineKind
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FloodBreakdown,
    RiskLevel,
    StaticFactors,
)
from limen.core.scoring import registry
from limen.core.scoring.flood import FloodScoringEngine, fluvial_trigger, pluvial_trigger
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds


def _thresholds() -> FloodThresholds:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    return t


def _bundle(
    *,
    susceptibility: float | None = 0.8,
    rain_mm: float | None = None,
    discharge_ratio: float | None = None,
    soil: float | None = 0.35,
    imperviousness: float | None = None,
) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="cell",
        static=StaticFactors(
            cell_id="cell",
            flood_hazard_norm=susceptibility,
            imperviousness_norm=imperviousness,
        ),
        dynamic=DynamicInputs(
            valuation_time=dt.datetime(2026, 11, 3, 12, tzinfo=dt.UTC),
            flood_forecast_rain_72h_mm=rain_mm,
            river_discharge_ratio=discharge_ratio,
            soil_moisture_0_7=soil,
        ),
    )


# ---------------------------------------------------------------------------
# Purezza
# ---------------------------------------------------------------------------
def test_scoring_the_same_bundle_twice_gives_the_same_answer() -> None:
    engine = FloodScoringEngine(_thresholds())
    b = _bundle(rain_mm=120.0)
    assert engine.score(b) == engine.score(b)


# ---------------------------------------------------------------------------
# La forma della combinazione
# ---------------------------------------------------------------------------
def test_the_two_triggers_combine_by_maximum_not_by_sum() -> None:
    """Una cella non è più allagata perché potrebbero accadere entrambi.

    Sono due modi diversi perché la stessa cella finisca sott'acqua; conta il
    peggiore, che è quello su cui un operatore deve pianificare. Sommarli
    lascerebbe che due segnali moderati ne inventino uno grave.
    """
    engine = FloodScoringEngine(_thresholds())
    only_rain = engine.score(_bundle(rain_mm=200.0)).score
    only_river = engine.score(_bundle(discharge_ratio=10.0)).score
    both = engine.score(_bundle(rain_mm=200.0, discharge_ratio=10.0)).score

    assert both == max(only_rain, only_river)
    assert both < only_rain + only_river


def test_susceptibility_multiplies_it_does_not_add() -> None:
    """L'acqua va in basso: un crinale non si allaga per quanto piova accanto.

    È la differenza con il motore incendio, dove un termine `base` tiene la
    roccia nuda sopra zero perché il fuoco ci arriva da fuori. Qui non esiste
    l'analogo, e sotto la soglia di terra asciutta il motore va a zero.
    """
    engine = FloodScoringEngine(_thresholds())
    t = _thresholds()

    ridge = engine.score(_bundle(susceptibility=0.0, rain_mm=300.0, discharge_ratio=50.0))
    assert ridge.score == 0.0
    assert ridge.level is RiskLevel.None_

    just_above_floor = engine.score(
        _bundle(susceptibility=t.susceptibility.floor + 0.01, rain_mm=300.0)
    )
    assert just_above_floor.score > 0.0


def test_an_unmapped_cell_is_not_a_safe_cell() -> None:
    """Il mosaico copre i bacini ufficialmente studiati.

    "Non studiato" non è "non allagabile": una cella fuori mappa prende un
    valore di ripiego basso — visibile ma incapace di arrivare in classe alta
    con la sola pioggia — e il breakdown dichiara che non è mappata.
    """
    engine = FloodScoringEngine(_thresholds())
    t = _thresholds()

    unmapped = engine.score(_bundle(susceptibility=None, rain_mm=300.0, discharge_ratio=50.0))
    assert unmapped.breakdown.mapped is False
    assert unmapped.score == pytest.approx(t.susceptibility.unmapped)
    assert unmapped.level is not RiskLevel.VeryHigh
    assert unmapped.score > 0.0


# ---------------------------------------------------------------------------
# Trigger pluviale
# ---------------------------------------------------------------------------
def test_rain_below_the_threshold_does_nothing() -> None:
    """La soglia intensità-durata è il punto sotto cui il drenaggio regge."""
    t = _thresholds()
    assert (
        pluvial_trigger(
            t.pluvial.threshold_mm - 1.0,
            soil_moisture=1.0,
            imperviousness=1.0,
            pluvial=t.pluvial,
            imperviousness_cfg=t.imperviousness,
        )
        == 0.0
    )


def test_dry_soil_damps_the_same_rain() -> None:
    """La prima pioggia se la beve il terreno; su suolo saturo scorre."""
    t = _thresholds()
    rain = 100.0
    dry = pluvial_trigger(
        rain,
        soil_moisture=0.0,
        imperviousness=None,
        pluvial=t.pluvial,
        imperviousness_cfg=t.imperviousness,
    )
    wet = pluvial_trigger(
        rain,
        soil_moisture=1.0,
        imperviousness=None,
        pluvial=t.pluvial,
        imperviousness_cfg=t.imperviousness,
    )
    assert 0.0 < dry < wet


def test_unknown_soil_moisture_neither_damps_nor_amplifies() -> None:
    """Indovinare "asciutto" sopprimerebbe un'allerta vera, indovinare
    "bagnato" ne inventerebbe una."""
    t = _thresholds()
    unknown = pluvial_trigger(
        100.0,
        soil_moisture=None,
        imperviousness=None,
        pluvial=t.pluvial,
        imperviousness_cfg=t.imperviousness,
    )
    saturated = pluvial_trigger(
        100.0,
        soil_moisture=t.pluvial.wet_soil,
        imperviousness=None,
        pluvial=t.pluvial,
        imperviousness_cfg=t.imperviousness,
    )
    assert unknown == saturated


def test_sealed_ground_amplifies_only_the_pluvial_branch() -> None:
    """Il cemento non fa crescere un fiume.

    A parità di tutto, una cella impermeabilizzata prende un punteggio più
    alto se il trigger dominante è la pioggia, e identico se è il fiume.
    """
    engine = FloodScoringEngine(_thresholds())
    rain_sealed = engine.score(_bundle(rain_mm=90.0, imperviousness=0.9)).score
    rain_porous = engine.score(_bundle(rain_mm=90.0, imperviousness=0.0)).score
    assert rain_sealed > rain_porous

    river_sealed = engine.score(_bundle(discharge_ratio=10.0, imperviousness=0.9)).score
    river_porous = engine.score(_bundle(discharge_ratio=10.0, imperviousness=0.0)).score
    assert river_sealed == river_porous


# ---------------------------------------------------------------------------
# Trigger fluviale
# ---------------------------------------------------------------------------
def test_a_river_at_its_normal_flow_does_not_trigger() -> None:
    t = _thresholds()
    assert fluvial_trigger(t.fluvial.normal_ratio, fluvial=t.fluvial) == 0.0
    assert fluvial_trigger(None, fluvial=t.fluvial) == 0.0
    assert fluvial_trigger(t.fluvial.saturation_ratio, fluvial=t.fluvial) == 1.0


def test_the_breakdown_keeps_the_raw_signals() -> None:
    """Un operatore che contesta un punteggio deve poter risalire ai numeri
    grezzi, non solo ai due trigger normalizzati."""
    engine = FloodScoringEngine(_thresholds())
    b = engine.score(_bundle(rain_mm=88.0, discharge_ratio=3.2)).breakdown
    assert b.rain_mm == 88.0
    assert b.discharge_ratio == 3.2


# ---------------------------------------------------------------------------
# Registry e configurazione
# ---------------------------------------------------------------------------
def test_flood_is_registered_with_its_own_breakdown() -> None:
    assert registry.is_registered(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    assert (
        registry.registered_breakdown(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
        is FloodBreakdown
    )
    engine = registry.resolve(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    assert isinstance(engine, FloodScoringEngine)


def test_the_registry_refuses_the_wrong_hazard_configuration() -> None:
    landslide = load_hazard_thresholds(HazardType.LANDSLIDE)
    with pytest.raises(TypeError, match="flood engine needs FloodThresholds"):
        registry.resolve(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC, thresholds=landslide)


def test_a_saturation_below_its_threshold_is_refused() -> None:
    """Invertirle darebbe una rampa a pendenza negativa: più pioggia, meno
    rischio, senza che nulla lo segnali."""
    base = load_hazard_thresholds(HazardType.FLOOD).model_dump()
    with pytest.raises(ValueError, match="must exceed"):
        FloodThresholds.model_validate(
            {**base, "pluvial": {**base["pluvial"], "saturation_mm": 10.0}}
        )
    with pytest.raises(ValueError, match="must exceed"):
        FloodThresholds.model_validate(
            {**base, "fluvial": {"normal_ratio": 4.0, "saturation_ratio": 2.0}}
        )


def test_every_enum_hazard_now_has_a_schema_and_an_engine() -> None:
    """Il criterio di #57 messo alla prova per la terza volta: aggiungere un
    pericolo è uno YAML più una registrazione."""
    from limen.core.scoring.regional_thresholds import SCHEMA_BY_HAZARD
    from limen.core.scoring.resolver import check_scorable

    for hazard in HazardType:
        assert hazard in SCHEMA_BY_HAZARD, hazard
        check_scorable(hazard)
