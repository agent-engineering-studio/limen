"""Un terremoto forte abbassa la soglia di pioggia della cella, e lei risale piano (#441)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.cli.backtest import soglia_pioggia_da_env, soglie_backtest
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    SogliaPioggiaSismica,
    load_regional_thresholds,
)
from limen.core.scoring.seismic_decay import riduzione_soglia_pioggia

ORA = datetime(2016, 10, 30, 12, 0, tzinfo=UTC)
SOGLIA = SogliaPioggiaSismica(riduzione_max=0.5, memoria_giorni=365.0, lookback_giorni=1095)


def _soglie(soglia: SogliaPioggiaSismica | None = SOGLIA) -> RegionalThresholds:
    base = load_regional_thresholds()
    seismic = base.seismic.model_copy(update={"soglia_pioggia": soglia})
    return base.model_copy(update={"seismic": seismic})


def _scossa(*, giorni_fa: float, pga_g: float, magnitudo: float = 6.0) -> SeismicHistoryEvent:
    return SeismicHistoryEvent(
        event_id=f"ev-{giorni_fa}-{pga_g}",
        origin_time=ORA - timedelta(days=giorni_fa),
        magnitude=magnitudo,
        distance_km=10.0,
        pga_g=pga_g,
    )


def _cella(scosse: list[SeismicHistoryEvent], *, mm_ora: float = 1.2) -> CellFeatureBundle:
    """12 ore a ``mm_ora``: 1,2 mm/h sta sotto la soglia nazionale (~1,75 mm/h a 12 h)."""
    inizio = ORA - timedelta(hours=12)
    pioggia = tuple(
        RainfallSample(timestamp=inizio + timedelta(hours=i + 1), precipitation_mm=mm_ora)
        for i in range(12)
    )
    return CellFeatureBundle(
        aoi_id="aoi-test",
        cell_id="c-test",
        static=StaticFactors(cell_id="c-test"),
        dynamic=DynamicInputs(
            valuation_time=ORA,
            rainfall=RainfallSeries(samples=pioggia),
            seismic_history=tuple(scosse),
        ),
    )


def test_senza_blocco_la_riduzione_e_zero() -> None:
    seismic = _soglie(None).seismic
    assert (
        riduzione_soglia_pioggia([_scossa(giorni_fa=1, pga_g=0.5)], as_of=ORA, seismic=seismic)
        == 0.0
    )
    assert seismic.giorni_da_leggere == seismic.lookback_days


def test_senza_blocco_il_punteggio_non_cambia() -> None:
    """Il motore della YAML e quello con il blocco tolto danno lo stesso punteggio."""
    cella = _cella([_scossa(giorni_fa=30, pga_g=0.4)])
    pacchetto = MultiFactorScoringEngine().score(cella)
    senza = MultiFactorScoringEngine(_soglie(None)).score(cella)
    assert pacchetto.score == senza.score
    assert senza.breakdown.meteo_terms.riduzione_sismica == 0.0


def test_la_riduzione_sale_con_la_pga_e_si_ferma_a_riduzione_max() -> None:
    seismic = _soglie().seismic
    valori = [
        riduzione_soglia_pioggia([_scossa(giorni_fa=0, pga_g=pga)], as_of=ORA, seismic=seismic)
        for pga in (0.01, 0.05, 0.1, 0.3, 2.0)
    ]
    assert valori[0] == 0.0  # sotto pga_min_g la cella non è scossa
    assert valori == sorted(valori)
    assert valori[-1] == pytest.approx(SOGLIA.riduzione_max, rel=1e-3)


def test_la_soglia_risale_con_la_memoria() -> None:
    seismic = _soglie().seismic
    oggi = riduzione_soglia_pioggia([_scossa(giorni_fa=0, pga_g=2.0)], as_of=ORA, seismic=seismic)
    un_anno = riduzione_soglia_pioggia(
        [_scossa(giorni_fa=365, pga_g=2.0)], as_of=ORA, seismic=seismic
    )
    assert un_anno == pytest.approx(oggi / 2.718281828, rel=1e-3)
    oltre = riduzione_soglia_pioggia(
        [_scossa(giorni_fa=1096, pga_g=2.0)], as_of=ORA, seismic=seismic
    )
    assert oltre == 0.0


def test_conta_la_scossa_piu_pesante_non_la_somma() -> None:
    seismic = _soglie().seismic
    forte = _scossa(giorni_fa=10, pga_g=0.3)
    debole = _scossa(giorni_fa=1, pga_g=0.06)
    insieme = riduzione_soglia_pioggia([forte, debole], as_of=ORA, seismic=seismic)
    da_sola = riduzione_soglia_pioggia([forte], as_of=ORA, seismic=seismic)
    assert insieme == da_sola


def test_le_scosse_piccole_e_quelle_future_non_contano() -> None:
    seismic = _soglie().seismic
    piccola = _scossa(giorni_fa=1, pga_g=0.5, magnitudo=seismic.min_magnitude - 0.1)
    futura = _scossa(giorni_fa=-1, pga_g=0.5)
    assert riduzione_soglia_pioggia([piccola, futura], as_of=ORA, seismic=seismic) == 0.0


def test_una_pioggia_sotto_soglia_supera_quella_abbassata() -> None:
    scossa = _scossa(giorni_fa=60, pga_g=0.4)
    senza = MultiFactorScoringEngine(_soglie(None)).score(_cella([scossa]))
    con = MultiFactorScoringEngine(_soglie()).score(_cella([scossa]))
    assert senza.breakdown.meteo_terms.caine_excess == 0.0
    assert con.breakdown.meteo_terms.caine_excess > 0.0
    assert con.breakdown.meteo_terms.riduzione_sismica > 0.0
    assert con.score > senza.score
    # E, il termine additivo, è lo stesso: dopo due mesi è decaduto a zero.
    assert con.breakdown.e == senza.breakdown.e == 0.0


def test_una_cella_non_scossa_resta_com_era() -> None:
    lontana = MultiFactorScoringEngine(_soglie()).score(_cella([]))
    senza = MultiFactorScoringEngine(_soglie(None)).score(_cella([]))
    assert lontana.score == senza.score


def test_anche_la_soglia_minima_del_tiering_scende() -> None:
    """Una cella scossa non si perde nel tiering per una pioggia ora pericolosa."""
    base = _soglie(None)
    if base.rain_floor is None:
        pytest.skip("nessun rain_floor nella YAML")
    scossa = _scossa(giorni_fa=30, pga_g=2.0)
    # Una pioggia appena sotto la soglia minima, che con la riduzione la supera.
    trovata = None
    for mm in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
        cella = _cella([scossa], mm_ora=mm)
        senza = MultiFactorScoringEngine(base).is_rescued_by_floor(cella)
        con = MultiFactorScoringEngine(_soglie()).is_rescued_by_floor(cella)
        assert con or not senza  # mai il contrario
        if con and not senza:
            trovata = mm
    assert trovata is not None


def test_lo_switch_del_backtest() -> None:
    assert soglia_pioggia_da_env("") == "yaml"
    assert soglia_pioggia_da_env(" no ") is None
    letta = soglia_pioggia_da_env("0.5,365")
    assert letta == SogliaPioggiaSismica(
        riduzione_max=0.5, memoria_giorni=365.0, lookback_giorni=1095
    )
    for storto in ("0.5", "1.5,365", "0.5,0", "a,b"):
        with pytest.raises(ValueError):
            soglia_pioggia_da_env(storto)


def test_soglie_backtest_sovrascrive_solo_quello_che_si_chiede() -> None:
    yaml = load_regional_thresholds()
    assert soglie_backtest() == yaml
    con = soglie_backtest(0.1, SOGLIA)
    assert con.seismic.pga_min_g == 0.1
    assert con.seismic.soglia_pioggia == SOGLIA
    assert con.seismic.giorni_da_leggere == 1095
    assert soglie_backtest(None, None).seismic.soglia_pioggia is None
