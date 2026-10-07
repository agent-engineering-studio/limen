"""Soglie della pioggia relative al clima del nodo (migrazione 065).

A Trieste 105 mm in tre giorni capitano circa una volta l'anno; con le soglie
nazionali (40 → 120 mm) davano «molto alto» a un autunno ordinario. Le soglie
locali sono il percentile della distribuzione del nodo che 40 mm
rappresentano nella regione di taratura, e non scendono mai sotto i 40 mm.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.core.models.hazard import HazardType
from limen.core.models.risk import CellFeatureBundle, DynamicInputs, StaticFactors
from limen.core.scoring.flood import FloodScoringEngine
from limen.core.scoring.flood.climatologia import (
    LIVELLI,
    livello_del_valore,
    quantili,
    somme_tre_giorni,
    valore_al_livello,
)
from limen.core.scoring.flood.trigger import soglie_pioggia
from limen.core.scoring.regional_thresholds import (
    FloodThresholds,
    PluvialLocalBlock,
    load_hazard_thresholds,
)

#: Il blocco provato il 7 ottobre 2026 e lasciato spento in `flood.yaml`: i
#: test lo accendono qui, perché il codice deve restare pronto.
_LOCALE = PluvialLocalBlock(threshold_level=0.965, saturation_ratio=3.0, floor_mm=40.0)


def _thresholds() -> FloodThresholds:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    return t.model_copy(update={"pluvial": t.pluvial.model_copy(update={"local": _LOCALE})})


def test_in_produzione_le_soglie_locali_sono_spente() -> None:
    """Il backtest le ha bocciate: perdevano alluvioni vere in Lombardia."""
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    assert t.pluvial.local is None


def _quantili_lineari(massimo: float) -> tuple[float, ...]:
    """Una distribuzione finta in cui il valore cresce col livello."""
    return tuple(massimo * lv for lv in LIVELLI)


def test_somme_su_tre_giorni() -> None:
    assert somme_tre_giorni([1, 2, 3, 4]) == [6, 9]


def test_quantili_e_inversa_si_ritrovano() -> None:
    q = quantili([float(i) for i in range(1001)])
    assert len(q) == len(LIVELLI)
    assert valore_al_livello(0.965, q) == pytest.approx(965.0, abs=0.5)
    assert livello_del_valore(965.0, q) == pytest.approx(0.965, abs=1e-3)


def test_senza_climatologia_valgono_le_soglie_nazionali() -> None:
    p = _thresholds().pluvial
    assert soglie_pioggia(p, None) == (p.threshold_mm, p.saturation_mm)


def test_spente_valgono_le_nazionali_anche_con_la_climatologia() -> None:
    p = load_hazard_thresholds(HazardType.FLOOD).model_dump()["pluvial"]
    spente = _thresholds().pluvial.model_copy(update={"local": None})
    assert soglie_pioggia(spente, _quantili_lineari(60.0)) == (
        p["threshold_mm"],
        p["saturation_mm"],
    )


def test_un_clima_piovoso_alza_la_soglia_e_tiene_il_rapporto() -> None:
    p = _thresholds().pluvial
    assert p.local is not None
    soglia, saturazione = soglie_pioggia(p, _quantili_lineari(60.0))
    assert soglia == pytest.approx(60.0 * p.local.threshold_level)
    assert saturazione == pytest.approx(soglia * p.local.saturation_ratio)


def test_un_clima_secco_non_scende_sotto_la_soglia_nazionale() -> None:
    p = _thresholds().pluvial
    assert p.local is not None
    soglia, _ = soglie_pioggia(p, _quantili_lineari(20.0))
    assert soglia == p.local.floor_mm


def _bundle(rain: float, q: tuple[float, ...] | None) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="cell",
        static=StaticFactors(cell_id="cell", flood_hazard_norm=0.8),
        dynamic=DynamicInputs(
            valuation_time=dt.datetime(2026, 10, 6, 12, tzinfo=dt.UTC),
            flood_forecast_rain_72h_mm=rain,
            soil_moisture_0_7=0.35,
            flood_rain_quantiles=q,
        ),
    )


def test_la_stessa_pioggia_pesa_meno_dove_e_ordinaria() -> None:
    """Trieste: soglia locale ~54 mm. 105 mm restano un segnale, non «molto alto»."""
    engine = FloodScoringEngine(_thresholds())
    nazionale = engine.score(_bundle(105.0, None))
    locale = engine.score(_bundle(105.0, _quantili_lineari(56.0)))
    assert locale.score < nazionale.score
    assert locale.breakdown.rain_threshold_mm == pytest.approx(56.0 * 0.965)
    assert nazionale.breakdown.rain_threshold_mm == 40.0
    payload = locale.breakdown.factors_payload()
    assert payload["rain_threshold_mm"] == locale.breakdown.rain_threshold_mm


def test_quante_volte_l_anno() -> None:
    """Uniforme fra 0 e 1000 su 3000 giorni: sopra il 99 % ⇒ ~1,2 eventi l'anno."""
    from limen.core.scoring.flood.climatologia import volte_l_anno

    q = quantili([float(i) for i in range(1001)])
    assert volte_l_anno(990.0, q) == pytest.approx(0.01 * 365.25 / 3, rel=0.05)
    assert volte_l_anno(2000.0, q) == 0.0
    assert volte_l_anno(10.0, q) is None
