"""Severità del bruciato da FRP nel fattore F (issue #67).

Tre gruppi di prove, nell'ordine in cui contano:

1. **Invarianza.** Senza severità disponibile il punteggio deve essere
   identico a prima della #67, altrimenti la modulazione avrebbe ricalibrato
   il campione di produzione di nascosto.
2. **Modulazione.** La severità cambia l'ampiezza e non la forma della
   campana, e il moltiplicatore è ≤ 1 per costruzione — può solo attenuare un
   allarme, mai inventarne uno.
3. **Normalizzazione.** La rampa FRP legge i suoi estremi dallo YAML, non dal
   codice, e `None` non diventa 0: "non misurato" e "bruciato debolmente" sono
   fatti diversi.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.post_fire import frp_severity, post_fire_factor, severity_multiplier
from limen.core.scoring.regional_thresholds import (
    PostFireBlock,
    RegionalThresholds,
    load_regional_thresholds,
)


def _post_fire(**overrides: float) -> PostFireBlock:
    base = load_regional_thresholds().post_fire
    return PostFireBlock(
        peak_months=base.peak_months,
        curve_denominator=base.curve_denominator,
        window_months_max=base.window_months_max,
        severity_floor=overrides.get("severity_floor", base.severity_floor),
        frp_floor_mw_per_ha=overrides.get("frp_floor_mw_per_ha", base.frp_floor_mw_per_ha),
        frp_saturation_mw_per_ha=overrides.get(
            "frp_saturation_mw_per_ha", base.frp_saturation_mw_per_ha
        ),
    )


def _bundle(*, months: float | None, severity: float | None) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="cell",
        static=StaticFactors(cell_id="cell", slope_deg=25.0, iffi_density_500=2.0),
        dynamic=DynamicInputs(
            valuation_time=dt.datetime(2026, 9, 1, 12, tzinfo=dt.UTC),
            months_since_fire=months,
            fire_severity=severity,
        ),
    )


# ---------------------------------------------------------------------------
# 1. Invarianza
# ---------------------------------------------------------------------------
def test_without_severity_the_factor_is_the_pre_67_bell() -> None:
    """La formula di prima, ricalcolata a mano: nessuna deriva silenziosa."""
    block = _post_fire()
    expected = math.exp(-((6.0 - block.peak_months) ** 2) / block.curve_denominator)

    assert post_fire_factor(6.0, post_fire=block) == pytest.approx(expected)
    assert post_fire_factor(6.0, post_fire=block, severity=None) == pytest.approx(expected)


def test_without_severity_the_whole_score_is_unchanged() -> None:
    """Regressione sul breakdown, non solo su F.

    È il criterio che protegge il campione di produzione: la #67 non deve
    spostare un punteggio finché una severità non è davvero misurata.
    """
    shipped = load_regional_thresholds()
    # Il motore "prima della #67": la modulazione disattivata da YAML è
    # esattamente il comportamento precedente, quindi è il riferimento contro
    # cui confrontare. Confrontare due `None` fra loro sarebbe vero per
    # costruzione e non proverebbe niente.
    payload = shipped.model_dump()
    payload["post_fire"]["severity_floor"] = 1.0
    pre_67 = MultiFactorScoringEngine(RegionalThresholds.model_validate(payload))
    engine = MultiFactorScoringEngine(shipped)

    without = engine.score(_bundle(months=6.0, severity=None))
    baseline = pre_67.score(_bundle(months=6.0, severity=1.0))

    assert without.score == pytest.approx(baseline.score)
    assert without.breakdown.f == pytest.approx(baseline.breakdown.f)
    assert without.breakdown.f > 0.0, "il caso deve essere dentro la finestra"
    assert without.breakdown.fire_severity_multiplier == 1.0
    assert without.breakdown.fire_severity is None
    # E il payload persistito non guadagna chiavi: le righe già scritte in
    # `risk_assessments` devono restare leggibili dallo stesso lettore.
    assert set(without.breakdown.factors_payload()) == {
        "s",
        "m",
        "e",
        "f",
        "h",
        "static_terms",
        "meteo_terms",
    }


def test_severity_floor_of_one_disables_the_modulation() -> None:
    """L'interruttore per tornare al comportamento precedente da YAML."""
    block = _post_fire(severity_floor=1.0)

    for severity in (0.0, 0.5, 1.0):
        assert post_fire_factor(6.0, post_fire=block, severity=severity) == pytest.approx(
            post_fire_factor(6.0, post_fire=block)
        )


# ---------------------------------------------------------------------------
# 2. Modulazione
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("severity", "expected_multiplier"),
    [(0.0, 0.5), (0.5, 0.75), (1.0, 1.0)],
)
def test_severity_scales_the_amplitude_between_floor_and_one(
    severity: float, expected_multiplier: float
) -> None:
    block = _post_fire(severity_floor=0.5)
    bell = post_fire_factor(6.0, post_fire=block)

    assert severity_multiplier(severity, post_fire=block) == pytest.approx(expected_multiplier)
    assert post_fire_factor(6.0, post_fire=block, severity=severity) == pytest.approx(
        bell * expected_multiplier
    )


def test_the_multiplier_can_never_exceed_one() -> None:
    """La proprietà che rende accettabile un `severity_floor` scelto a giudizio:
    la severità può solo attenuare un allarme, non inventarne uno."""
    block = _post_fire(severity_floor=0.5)

    for severity in (0.0, 0.25, 0.5, 0.75, 1.0, 5.0):
        assert severity_multiplier(severity, post_fire=block) <= 1.0


def test_severity_does_not_move_the_peak() -> None:
    """Modula l'ampiezza, non la forma: l'idrofobicità decorre allo stesso
    modo, cambia quanto è intensa, non quando."""
    block = _post_fire(severity_floor=0.3)
    months = [0.0, 3.0, 6.0, 12.0, 24.0]

    full = [post_fire_factor(m, post_fire=block, severity=1.0) for m in months]
    weak = [post_fire_factor(m, post_fire=block, severity=0.0) for m in months]

    assert full.index(max(full)) == weak.index(max(weak))
    ratios = [w / f for w, f in zip(weak, full, strict=True) if f > 0]
    assert all(r == pytest.approx(ratios[0]) for r in ratios)


def test_outside_the_window_severity_changes_nothing() -> None:
    block = _post_fire(severity_floor=0.5)

    assert post_fire_factor(None, post_fire=block, severity=1.0) == 0.0
    assert post_fire_factor(99.0, post_fire=block, severity=1.0) == 0.0


# ---------------------------------------------------------------------------
# 3. Normalizzazione FRP
# ---------------------------------------------------------------------------
def test_frp_ramp_reads_its_ends_from_the_yaml() -> None:
    """Nessuna costante nel codice: l'override sposta la rampa."""
    block = _post_fire(frp_floor_mw_per_ha=1.0, frp_saturation_mw_per_ha=3.0)

    assert frp_severity(0.5, post_fire=block) == 0.0
    assert frp_severity(1.0, post_fire=block) == 0.0
    assert frp_severity(2.0, post_fire=block) == pytest.approx(0.5)
    assert frp_severity(3.0, post_fire=block) == 1.0
    assert frp_severity(10.0, post_fire=block) == 1.0


def test_unmeasured_density_stays_none_instead_of_zero() -> None:
    """Schiacciare `None` su 0 attenuerebbe l'allarme ogni volta che un
    perimetro non ha hotspot dentro — un dato mancante letto come una misura."""
    assert frp_severity(None, post_fire=_post_fire()) is None


def test_ramp_with_inverted_ends_is_a_configuration_error() -> None:
    block = _post_fire(frp_floor_mw_per_ha=2.0, frp_saturation_mw_per_ha=1.0)

    with pytest.raises(ValueError, match="frp_saturation_mw_per_ha"):
        frp_severity(1.5, post_fire=block)


def test_the_shipped_ramp_matches_the_measured_distribution() -> None:
    """I default non sono numeri tondi scelti a naso: sono il p10 e il p90
    della densità misurata su 2.419 perimetri EFFIS italiani."""
    block = load_regional_thresholds().post_fire

    assert block.frp_floor_mw_per_ha == pytest.approx(0.08)
    assert block.frp_saturation_mw_per_ha == pytest.approx(0.88)
    # La mediana misurata (0,273) cade nel terzo inferiore della rampa.
    median_severity = frp_severity(0.273, post_fire=block)
    assert median_severity is not None
    assert 0.15 < median_severity < 0.35


def test_thresholds_schema_rejects_a_non_positive_saturation() -> None:
    base = load_regional_thresholds()
    payload = base.model_dump()
    payload["post_fire"]["frp_saturation_mw_per_ha"] = 0.0

    with pytest.raises(ValueError, match="frp_saturation_mw_per_ha"):
        RegionalThresholds.model_validate(payload)
