"""I mancati del backtest incendio, con la causa (#714).

Il punteggio è ``fwi_norm * (base + fuel*f + slope*s)``; con il YAML vero il
tessuto urbano (CORINE 111) ha terreno 0,28 e combustibile 0,05, sotto il
cancello degli avvisi (0,3). Tre celle urbane, tre catene: FWI 5 non arriva
a «Moderato» neanche col terreno pieno, FWI 30 ci arriverebbe ma il terreno
lo tiene sotto, FWI 50 ci arriva e lo ferma il cancello.
"""

from __future__ import annotations

from datetime import date, timedelta

from limen.cli.backtest_wildfire import (
    CAUSA_CANCELLO,
    CAUSA_METEO,
    CAUSA_SENZA_METEO,
    CAUSA_TERRENO,
    WildfireBacktestMetrics,
    causa,
    evaluate,
    mancati_report,
    terra_corine,
)
from limen.core.models.hazard import HazardType
from limen.core.models.risk import FireWeatherState, RiskLevel, StaticFactors
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds

INIZIO = date(2025, 7, 1)
INCENDIO = INIZIO + timedelta(days=5)
NODI = [(10.0, 45.0), (11.0, 45.0), (12.0, 45.0), (13.0, 45.0)]


def _soglie() -> WildfireThresholds:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    return t


def _catena(fwi: float) -> dict[date, FireWeatherState]:
    return {
        INIZIO + timedelta(days=i): FireWeatherState(
            day=INIZIO + timedelta(days=i),
            ffmc=90,
            dmc=40,
            dc=400,
            isi=8,
            bui=60,
            fwi=fwi,
            chain_days=60 + i,
        )
        for i in range(6)
    }


def _valuta() -> WildfireBacktestMetrics:
    celle = ["meteo", "terreno", "cancello", "vuota"]
    return evaluate(
        aoi_id="it-x",
        truth={c: (INCENDIO, lon, lat) for c, (lon, lat) in zip(celle, NODI, strict=True)},
        static={c: StaticFactors(cell_id=c, landuse_code="111", slope_deg=0.0) for c in celle},
        nodes=NODI,
        chains=[_catena(5.0), _catena(30.0), _catena(50.0), {}],
        days=[INIZIO + timedelta(days=i) for i in range(6)],
        thresholds=_soglie(),
        alert_level=RiskLevel.Moderate,
    )


def test_ogni_mancato_ha_la_sua_causa() -> None:
    m = _valuta()
    assert m.hits == 0 and m.misses == 4
    assert m.soglia == _soglie().classes.moderate.lo
    cause = {x.cell_id: x.causa for x in m.mancati}
    assert cause == {
        "meteo": CAUSA_METEO,
        "terreno": CAUSA_TERRENO,
        "cancello": CAUSA_CANCELLO,
        "vuota": CAUSA_SENZA_METEO,
    }
    terreno = next(x for x in m.mancati if x.cell_id == "terreno")
    assert terreno.fwi == 30.0 and terreno.terreno is not None
    assert terreno.punteggio is not None and terreno.fwi_norm is not None
    assert abs(terreno.punteggio - terreno.fwi_norm * terreno.terreno) < 1e-9


def test_causa_dai_massimi() -> None:
    assert causa(fwi_norm=None, punteggio=None, soglia=0.24) == CAUSA_SENZA_METEO
    assert causa(fwi_norm=0.1, punteggio=0.05, soglia=0.24) == CAUSA_METEO
    assert causa(fwi_norm=0.5, punteggio=0.2, soglia=0.24) == CAUSA_TERRENO
    assert causa(fwi_norm=0.9, punteggio=0.3, soglia=0.24) == CAUSA_CANCELLO


def test_la_sezione_conta_per_causa_terra_e_mese() -> None:
    m = _valuta()
    righe = "\n".join(mancati_report(m.mancati, soglia=m.soglia))
    assert "## Mancati, con la causa" in righe
    assert f"{CAUSA_METEO} 1" in righe and f"{CAUSA_CANCELLO} 1" in righe
    assert "artificiale 4" in righe
    assert "07: 4" in righe
    assert "| vuota | 2025-07-06 | 111 | — |" in righe
    assert mancati_report((), soglia=0.24) == []


def test_terra_corine() -> None:
    assert terra_corine("211") == "agricola"
    assert terra_corine("312") == "bosco e seminaturale"
    assert terra_corine(None) == "non nota"
