"""#483: il gate di promozione prende hit rate, falsi allarmi e anticipo dal backtest."""

from __future__ import annotations

import math
from array import array
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from limen.cli import backtest as bt
from limen.config.settings import Settings
from limen.core.models.risk import (
    CellFeatureBundle,
    RainfallSample,
    RiskLevel,
    StaticFactors,
)
from limen.ml.promozione import (
    EsitoBacktest,
    gate_backtest,
    gate_validazione,
    unisci,
)

INIZIO = datetime(2019, 11, 20, tzinfo=UTC)
FINE = INIZIO + timedelta(hours=72)
EVENTO = INIZIO + timedelta(hours=60)


@pytest.fixture
def settings() -> Settings:
    return Settings.model_validate({})


def _esito(**kw: float) -> EsitoBacktest:
    base: dict[str, float] = {
        "eventi": 10,
        "colti": 8,
        "falsi_allarmi": 2,
        "anticipo_medio_ore": 24.0,
        "celle": 1000,
        "celle_ore": 72_000,
        "celle_ore_in_allerta": 700,
    }
    base.update(kw)
    return EsitoBacktest(**base)  # type: ignore[arg-type]  # kw float per brevità, i campi int arrivano interi


def test_la_validazione_boccia_un_modello_che_non_batte_la_v1(settings: Settings) -> None:
    assert not gate_validazione(settings, ml_auc_pr=0.60, ml_brier=0.10, baseline_auc_pr=0.65)
    assert gate_validazione(settings, ml_auc_pr=0.70, ml_brier=0.10, baseline_auc_pr=0.55)


def test_il_backtest_boccia_su_anticipo_e_falsi_allarmi(settings: Settings) -> None:
    v1 = _esito(colti=7)
    assert gate_backtest(settings, _esito(), v1)
    assert not gate_backtest(settings, _esito(anticipo_medio_ore=0.0), v1)
    assert not gate_backtest(settings, _esito(colti=4, falsi_allarmi=6), v1)
    assert not gate_backtest(settings, _esito(eventi=0, colti=0, falsi_allarmi=0), v1)


def test_il_backtest_vuole_almeno_la_v1_e_non_piu_allerte(settings: Settings) -> None:
    """Sopra i minimi assoluti non basta: lo sfidante deve battere la V1 alla pari."""
    assert not gate_backtest(settings, _esito(colti=8), _esito(colti=9))
    assert not gate_backtest(settings, _esito(celle_ore_in_allerta=900), _esito(colti=7))


def test_unisci_pesa_l_anticipo_sugli_eventi_colti() -> None:
    a = _esito(eventi=4, colti=4, anticipo_medio_ore=30.0, celle=100, celle_ore=7200)
    b = _esito(eventi=2, colti=1, anticipo_medio_ore=0.0, celle=300, celle_ore=21600)
    u = unisci([a, b])
    assert u.hit_rate == pytest.approx(5 / 6)
    assert u.anticipo_medio_ore == pytest.approx(24.0)
    assert u.tasso_base == pytest.approx(6 / 400)


@dataclass(frozen=True)
class _Punteggio:
    """Il backtest legge solo punteggio e classe."""

    score: float
    level: RiskLevel


class _Profeta:
    """Uno sfidante finto: la cella dell'evento sale 24 ore prima, le altre restano basse."""

    def __init__(self, cella: str, valori_altre: Sequence[float]) -> None:
        self._cella = cella
        self._altre = list(valori_altre)

    def _uno(self, b: CellFeatureBundle, i: int) -> _Punteggio:
        t = b.dynamic.valuation_time
        if b.cell_id == self._cella:
            valore = 0.9 if EVENTO - timedelta(hours=24) <= t < EVENTO else 0.01
        else:
            valore = self._altre[i % len(self._altre)]
        # La classe sbagliata apposta: con `carico` conta il punteggio.
        return _Punteggio(score=valore, level=RiskLevel.None_)

    def score(self, bundle: CellFeatureBundle) -> _Punteggio:
        return self._uno(bundle, 0)

    def score_many(self, bundles: Sequence[CellFeatureBundle]) -> Sequence[_Punteggio]:
        return [self._uno(b, i) for i, b in enumerate(bundles)]


def test_uno_sfidante_che_vede_24_ore_prima_passa_il_gate(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Il criterio della issue: oggi `promoted` resta False con qualunque modello."""
    monkeypatch.setattr(bt, "REPORTS_DIR", tmp_path)
    celle = [(StaticFactors(cell_id=f"c{i}"), 16.0 + i * 0.01, 40.0) for i in range(10)]
    pioggia = [
        RainfallSample(timestamp=INIZIO + timedelta(hours=h), precipitation_mm=0.0)
        for h in range(73)
    ]
    m = bt._evaluate(
        aoi_id="it-prova",
        cells=celle,
        nodes=[(16.0, 40.0)],
        node_rainfall=[pioggia],
        truth={"c3": EVENTO},
        start=INIZIO,
        end=FINE,
        alert_level=RiskLevel.High,
        lead_max_hours=48.0,
        engine=_Profeta("c3", [0.05, 0.02, 0.03]),  # type: ignore[arg-type]  # finto duck-typed, legge solo score/level
        carico=24 / (72 * 10),
        motore="sfidante v1",
    )
    esito = m.esito()
    assert esito.colti == 1
    assert esito.falsi_allarmi == 0
    assert esito.anticipo_medio_ore == pytest.approx(24.0)
    assert esito.quota_allertate == pytest.approx(24 / esito.celle_ore, rel=0.05)
    assert gate_backtest(settings, esito, esito)
    assert m.report_path.name.endswith("_sfidante.md")


def test_la_soglia_a_quota_non_accende_lo_zero() -> None:
    righe = [array("f", [0.0, 0.0, 0.0]), array("f", [0.0, 0.5, 0.0])]
    assert bt._soglia_quota(righe, 0.5) == pytest.approx(0.5)


def test_il_pari_merito_non_sfora_la_quota() -> None:
    """Gradini isotonici: chiedere 2 celle-ora su un gradino di 4 non ne accende 4."""
    righe = [array("f", [0.9, 0.3, 0.3, 0.3, 0.3, 0.1])]
    assert bt._soglia_quota(righe, 2 / 6) == pytest.approx(0.9)


def test_quota_zero_non_accende_niente() -> None:
    assert bt._soglia_quota([array("f", [0.9, 0.1])], 0.0) == math.inf
