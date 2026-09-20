"""La curva regionale viene scelta davvero (#122).

Le quattro curve di Caine ritarate su e-ITALICA erano configurazione morta:
`macroregion` esisteva in quattro punti e in tutti e quattro restava al
default, quindi l'Italia intera girava su `italy_default`. Questi test
fissano il comportamento nuovo — la risoluzione avviene nel motore, a
partire dall'AOI del bundle — perché è esattamente il tipo di difetto che
nessun test vedeva.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    load_regional_thresholds,
)

VALUATION_TIME = datetime(2024, 11, 1, 12, tzinfo=UTC)


def _bundle(aoi_id: str, *, macroregion: str | None = None) -> CellFeatureBundle:
    # 60 mm in 24 h: sopra la soglia di tutte le macroregioni, ma di quanto
    # dipende dalla curva — è la differenza che questi test misurano.
    samples = tuple(
        RainfallSample(timestamp=VALUATION_TIME - timedelta(hours=h), precipitation_mm=2.5)
        for h in range(24, 0, -1)
    )
    static = StaticFactors(
        cell_id="c-test",
        iffi_density_500=4,
        slope_deg=27.0,
        pai_class_norm=0.75,
        litho_weight=0.6,
    )
    return CellFeatureBundle(
        aoi_id=aoi_id,
        cell_id="c-test",
        static=static,
        macroregion=macroregion,
        dynamic=DynamicInputs(
            valuation_time=VALUATION_TIME,
            rainfall=RainfallSeries(samples=samples),
            api_30_mm=95.0,
            soil_moisture_0_7=0.38,
        ),
    )


@pytest.mark.parametrize(
    ("aoi_id", "expected"),
    [
        ("it-basilicata", "southern_italy"),
        ("it-puglia", "southern_italy"),
        ("it-liguria", "northern_italy"),
        ("it-lazio", "central_italy"),
    ],
)
def test_assignment_follows_the_yaml(aoi_id: str, expected: str) -> None:
    assert load_regional_thresholds().macroregion_for(aoi_id) == expected


def test_unknown_aoi_falls_back_to_the_generic_curve() -> None:
    # Una AOI nuova deve poter essere valutata prima che qualcuno decida in
    # quale gruppo sta: il fallback e' la curva prudente, non un errore.
    assert load_regional_thresholds().macroregion_for("it-inesistente") == "italy_default"


def test_same_cell_scores_differently_by_region() -> None:
    engine = MultiFactorScoringEngine(load_regional_thresholds())
    south = engine.score(_bundle("it-basilicata")).score
    north = engine.score(_bundle("it-liguria")).score
    generic = engine.score(_bundle("it-inesistente")).score

    # Al sud la soglia e' piu' bassa (39,9 mm/72 h contro 51,3 al nord),
    # quindi la stessa pioggia eccede di piu' e il punteggio e' piu' alto.
    # Prima della #122 i tre numeri erano identici.
    assert south > generic > north


def test_an_explicit_macroregion_still_wins() -> None:
    engine = MultiFactorScoringEngine(load_regional_thresholds())
    forced = engine.score(_bundle("it-liguria", macroregion="southern_italy")).score
    natural = engine.score(_bundle("it-basilicata")).score
    assert forced == pytest.approx(natural)


def test_yaml_naming_a_curve_that_does_not_exist_is_refused() -> None:
    # Un refuso nell'assegnazione deve fermare l'avvio, non far ricadere in
    # silenzio mezza Italia sulla curva generica.
    base = load_regional_thresholds().model_dump()
    base["macroregion_by_aoi"] = {"inesistente_italy": ["it-puglia"]}
    with pytest.raises(ValidationError, match="macroregion_by_aoi"):
        RegionalThresholds.model_validate(base)


def test_an_aoi_cannot_belong_to_two_macroregions() -> None:
    base = load_regional_thresholds().model_dump()
    base["macroregion_by_aoi"] = {
        "northern_italy": ["it-liguria"],
        "southern_italy": ["it-liguria"],
    }
    with pytest.raises(ValidationError, match="due macroregioni"):
        RegionalThresholds.model_validate(base)
