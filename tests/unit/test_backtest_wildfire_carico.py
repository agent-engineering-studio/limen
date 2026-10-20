"""Il carico per cella del backtest incendio (#295).

Il conto prende una scorciatoia — il terreno chiesto al motore una volta per
cella, poi moltiplicato per i giorni del nodo — e deve dare esattamente ciò
che darebbe il motore valutando ogni cella in ogni giorno.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from limen.cli.backtest_wildfire import CellaAoi, carico_celle
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    RiskLevel,
    StaticFactors,
)
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.core.scoring.wildfire import WildfireScoringEngine

INIZIO = date(2025, 7, 1)
NODI = [(16.0, 40.0), (17.0, 40.0)]


def _soglie() -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t


def _catena(fwi: list[float]) -> dict[date, FireWeatherState]:
    return {
        INIZIO + timedelta(days=i): FireWeatherState(
            day=INIZIO + timedelta(days=i),
            ffmc=90,
            dmc=40,
            dc=400,
            isi=8,
            bui=60,
            fwi=v,
            chain_days=60 + i,
        )
        for i, v in enumerate(fwi)
    }


CELLE = [
    CellaAoi(
        "conifere-ripide",
        16.01,
        40.0,
        StaticFactors(cell_id="conifere-ripide", landuse_code="312", slope_deg=40.0),
    ),
    CellaAoi(
        "seminativo-piano",
        16.02,
        40.0,
        StaticFactors(cell_id="seminativo-piano", landuse_code="211", slope_deg=1.0),
    ),
    CellaAoi("citta", 16.98, 40.0, StaticFactors(cell_id="citta", landuse_code="111")),
    CellaAoi("ignota", 16.99, 40.0, StaticFactors(cell_id="ignota")),
]
CATENE = [_catena([5, 20, 30, 45, 60, 25]), _catena([70, 80, 10, 50, 40, 22])]


@pytest.mark.parametrize("livello", [RiskLevel.Moderate, RiskLevel.High, RiskLevel.VeryHigh])
def test_uguale_al_motore_cella_per_cella(livello: RiskLevel) -> None:
    t = _soglie()
    engine = WildfireScoringEngine(t)
    ordine = list(RiskLevel)
    giornate = in_allerta = 0
    for cella in CELLE:
        catena = CATENE[0] if cella.lon < 16.5 else CATENE[1]
        for giorno, stato in catena.items():
            livello_giorno = engine.score(
                CellFeatureBundle(
                    aoi_id="x",
                    cell_id=cella.cell_id,
                    static=cella.static,
                    dynamic=DynamicInputs(
                        valuation_time=datetime.combine(giorno, time(12), UTC),
                        fire_weather=stato,
                    ),
                )
            ).level
            giornate += 1
            in_allerta += ordine.index(livello_giorno) >= ordine.index(livello)
    atteso = in_allerta / giornate
    assert 0 < atteso < 1  # il caso deve distinguere qualcosa
    assert carico_celle(
        CELLE,
        nodes=NODI,
        chains=CATENE,
        start=INIZIO,
        end=INIZIO + timedelta(days=5),
        thresholds=t,
        alert_level=livello,
    ) == pytest.approx(atteso)


def test_fuori_stagione_non_conta() -> None:
    t = _soglie()
    carico = carico_celle(
        CELLE,
        nodes=NODI,
        chains=CATENE,
        start=INIZIO + timedelta(days=10),
        end=INIZIO + timedelta(days=20),
        thresholds=t,
        alert_level=RiskLevel.High,
    )
    assert carico == 0.0


def test_un_peso_piu_alto_accende_piu_territorio() -> None:
    """Il punto della metrica: il tasso di base sulle celle bruciate non lo vede."""
    t = _soglie()
    pesi = {**t.fuel.by_clc_prefix, "211": 1.0}
    alzato = t.model_copy(update={"fuel": t.fuel.model_copy(update={"by_clc_prefix": pesi})})

    def carico(soglie: WildfireThresholds) -> float:
        return carico_celle(
            CELLE,
            nodes=NODI,
            chains=CATENE,
            start=INIZIO,
            end=INIZIO + timedelta(days=5),
            thresholds=soglie,
            alert_level=RiskLevel.High,
        )

    assert carico(alzato) > carico(t)
