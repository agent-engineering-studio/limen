"""Motore incendio e configurazione wildfire (issue #61).

Il criterio dell'issue è che il motore sia **puro** e **registrato**. Qui si
verifica anche ciò che rende il pericolo aggiungibile senza toccare codice:
lo schema per pericolo, la mappatura CORINE, e il fatto che la legenda non
sappia più nulla di frane.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.config.settings import ScoringEngineKind
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    RiskLevel,
    StaticFactors,
    WildfireBreakdown,
)
from limen.core.scoring import registry
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire import WildfireScoringEngine


def _thresholds() -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t


def _bundle(
    *,
    fwi: float | None = 35.0,
    landuse: str | None = "323",
    slope_deg: float | None = 20.0,
    chain_days: int = 60,
) -> CellFeatureBundle:
    fire = (
        None
        if fwi is None
        else FireWeatherState(
            day=dt.date(2026, 7, 15),
            ffmc=92.0,
            dmc=60.0,
            dc=400.0,
            isi=12.0,
            bui=80.0,
            fwi=fwi,
            chain_days=chain_days,
        )
    )
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="cell",
        static=StaticFactors(cell_id="cell", landuse_code=landuse, slope_deg=slope_deg),
        dynamic=DynamicInputs(
            valuation_time=dt.datetime(2026, 7, 15, 12, tzinfo=dt.UTC), fire_weather=fire
        ),
    )


# ---------------------------------------------------------------------------
# Purezza — l'invariante di progetto
# ---------------------------------------------------------------------------
def test_scoring_the_same_bundle_twice_gives_the_same_answer() -> None:
    """Nessun orologio, nessuna rete, nessuno stato interno: il motore è una
    funzione. Se non lo fosse, due sweep sulla stessa cella potrebbero
    divergere e nessun backtest sarebbe riproducibile."""
    engine = WildfireScoringEngine(_thresholds())
    b = _bundle()
    assert engine.score(b) == engine.score(b)


# ---------------------------------------------------------------------------
# I tre termini
# ---------------------------------------------------------------------------
def test_the_three_terms_are_weighted_not_multiplied() -> None:
    """Roccia nuda in condizioni estreme non deve dare zero.

    Un prodotto azzererebbe il punteggio di una cella senza combustibile, e
    la cella accanto brucerà lo stesso: il fuoco ci arriva da fuori. La somma
    pesata è la scelta, e questo test la difende da una "semplificazione".
    """
    engine = WildfireScoringEngine(_thresholds())
    bare_rock = engine.score(_bundle(landuse="332", slope_deg=0.0))
    assert bare_rock.score > 0.0


def test_a_cell_without_a_chain_scores_but_cannot_reach_the_top() -> None:
    """Senza catena FWI il termine meteo è ignoto, non zero.

    La cella conserva il punteggio che combustibile e pendenza le danno —
    lasciarla al buio sarebbe peggio — ma senza il termine dominante non può
    finire in classe alta, che è la risposta onesta quando manca l'unico
    ingresso che varia nel tempo.
    """
    engine = WildfireScoringEngine(_thresholds())
    t = _thresholds()
    worst = engine.score(_bundle(fwi=None, landuse="312", slope_deg=90.0))
    assert worst.breakdown.fwi_norm == 0.0
    assert worst.score <= t.weights.fuel + t.weights.slope
    assert worst.level is not RiskLevel.VeryHigh


def test_the_fwi_term_saturates_at_the_configured_maximum() -> None:
    """Oltre il massimo EFFIS l'indice sale ma la risposta operativa no."""
    engine = WildfireScoringEngine(_thresholds())
    at_max = engine.score(_bundle(fwi=50.0))
    way_over = engine.score(_bundle(fwi=250.0))
    assert at_max.breakdown.fwi_norm == 1.0
    assert way_over.score == at_max.score


def test_conifers_outrank_farmland_at_identical_weather() -> None:
    """La mappatura CORINE deve ordinare il combustibile come la fisica."""
    engine = WildfireScoringEngine(_thresholds())
    conifer = engine.score(_bundle(landuse="312")).score
    scrub = engine.score(_bundle(landuse="323")).score
    farmland = engine.score(_bundle(landuse="211")).score
    water = engine.score(_bundle(landuse="512")).score
    assert conifer > scrub > farmland > water


def test_unknown_land_cover_is_not_read_as_incombustible() -> None:
    """Dato assente ≠ "non può bruciare". Una cella senza CORINE deve pesare
    quanto un'area agricola, non quanto un lago."""
    engine = WildfireScoringEngine(_thresholds())
    unknown = engine.score(_bundle(landuse=None)).score
    water = engine.score(_bundle(landuse="512")).score
    assert unknown > water


def test_spinup_is_declared_not_hidden() -> None:
    """Un FWI su tre giorni di storia non è sbagliato, è non ancora
    significativo: il punteggio esce comunque, con il flag alzato."""
    engine = WildfireScoringEngine(_thresholds())
    fresh = engine.score(_bundle(chain_days=3))
    settled = engine.score(_bundle(chain_days=200))
    assert fresh.breakdown.spinup is True
    assert settled.breakdown.spinup is False
    assert fresh.score == settled.score


def test_the_breakdown_carries_the_raw_chain() -> None:
    """Un operatore che contesta un punteggio deve poter risalire ai sei
    numeri di Van Wagner, non solo al termine normalizzato."""
    engine = WildfireScoringEngine(_thresholds())
    fw = engine.score(_bundle()).breakdown.fire_weather
    assert fw is not None
    assert fw.dc == 400.0


# ---------------------------------------------------------------------------
# Registry e configurazione
# ---------------------------------------------------------------------------
def test_wildfire_is_registered_with_its_own_breakdown() -> None:
    """Il criterio di accettazione dell'issue: registrato come `wildfire`."""
    assert registry.is_registered(HazardType.WILDFIRE, ScoringEngineKind.DETERMINISTIC)
    assert (
        registry.registered_breakdown(HazardType.WILDFIRE, ScoringEngineKind.DETERMINISTIC)
        is WildfireBreakdown
    )
    engine = registry.resolve(HazardType.WILDFIRE, ScoringEngineKind.DETERMINISTIC)
    assert isinstance(engine, WildfireScoringEngine)


def test_the_registry_refuses_the_wrong_hazard_configuration() -> None:
    """Costruire il motore incendio con le soglie delle frane darebbe numeri
    sbagliati presentati come giusti: meglio un errore rumoroso."""
    landslide = load_hazard_thresholds(HazardType.LANDSLIDE)
    with pytest.raises(TypeError, match="wildfire engine needs WildfireThresholds"):
        registry.resolve(HazardType.WILDFIRE, ScoringEngineKind.DETERMINISTIC, thresholds=landslide)


def test_each_hazard_validates_with_its_own_schema() -> None:
    """Due file, due forme. Se lo schema fosse uno solo, l'assenza del blocco
    Caine in wildfire.yaml passerebbe come "opzionale" invece che come
    "questo pericolo non ha una soglia pluviale"."""
    assert isinstance(load_hazard_thresholds(HazardType.LANDSLIDE), RegionalThresholds)
    assert isinstance(load_hazard_thresholds(HazardType.WILDFIRE), WildfireThresholds)


def test_the_model_card_is_built_by_the_configuration_not_the_endpoint() -> None:
    """La legenda serve qualunque pericolo: se l'endpoint leggesse i blocchi
    avrebbe un ramo per pericolo e si romperebbe al primo senza Caine."""
    landslide = load_hazard_thresholds(HazardType.LANDSLIDE).model_card()
    wildfire = load_hazard_thresholds(HazardType.WILDFIRE).model_card()
    assert "caine" in landslide
    assert "caine" not in wildfire
    assert wildfire["fwi"]["normalisation_max"] == 50.0


def test_wildfire_weights_must_sum_to_one() -> None:
    """Somma diversa da 1 sposterebbe silenziosamente la scala dei punteggi
    e, con essa, il significato dei cutoff di classe."""
    with pytest.raises(ValueError, match="must sum to 1"):
        WildfireThresholds.model_validate(
            {
                **load_hazard_thresholds(HazardType.WILDFIRE).model_dump(),
                "weights": {"fwi": 0.5, "fuel": 0.3, "slope": 0.3},
            }
        )
