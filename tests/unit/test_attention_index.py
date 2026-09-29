"""Il numero che porta un comune all'attenzione (redesign della colonna).

Fissa la scelta contro la somma, che era l'alternativa proposta: sommare i
tre punteggi inverte le priorità, e questi test lo dimostrano con due
comuni invece che con un'argomentazione.
"""

from __future__ import annotations

import pytest

from limen.core.cascades.attention import at_or_above, attention_index
from limen.core.cascades.config import AttentionRule
from limen.core.models.risk import RiskLevel

_REGOLA = AttentionRule(enabled=True, min_level=RiskLevel.Moderate, multi_hazard_bump=0.15)


def test_un_versante_grave_batte_tre_pericoli_blandi() -> None:
    # È il controesempio alla somma: 0,40 per 3 = 1,20 > 0,80, ma l'unico
    # comune dove sta per succedere qualcosa è il secondo.
    blandi = attention_index(
        {
            "landslide": (0.40, RiskLevel.Low),
            "flood": (0.40, RiskLevel.Low),
            "wildfire": (0.40, RiskLevel.Low),
        },
        rule=_REGOLA,
    )
    grave = attention_index({"landslide": (0.80, RiskLevel.High)}, rule=_REGOLA)
    assert grave > blandi


def test_due_pericoli_oltre_soglia_contano_piu_di_uno() -> None:
    uno = attention_index({"landslide": (0.60, RiskLevel.Moderate)}, rule=_REGOLA)
    due = attention_index(
        {"landslide": (0.60, RiskLevel.Moderate), "wildfire": (0.50, RiskLevel.Moderate)},
        rule=_REGOLA,
    )
    assert due == pytest.approx(uno * 1.15)


def test_ma_non_il_doppio() -> None:
    # L'incremento è una correzione, non una somma travestita.
    uno = attention_index({"landslide": (0.60, RiskLevel.Moderate)}, rule=_REGOLA)
    tre = attention_index(
        {
            "landslide": (0.60, RiskLevel.Moderate),
            "flood": (0.60, RiskLevel.Moderate),
            "wildfire": (0.60, RiskLevel.Moderate),
        },
        rule=_REGOLA,
    )
    assert tre < 2 * uno


def test_i_pericoli_sotto_soglia_non_fanno_incremento() -> None:
    solo = attention_index({"landslide": (0.60, RiskLevel.Moderate)}, rule=_REGOLA)
    con_calmi = attention_index(
        {
            "landslide": (0.60, RiskLevel.Moderate),
            "flood": (0.02, RiskLevel.None_),
            "wildfire": (0.05, RiskLevel.Low),
        },
        rule=_REGOLA,
    )
    assert con_calmi == pytest.approx(solo)


def test_la_regola_spenta_lascia_il_massimo() -> None:
    spenta = AttentionRule(enabled=False, min_level=RiskLevel.Moderate, multi_hazard_bump=0.5)
    assert attention_index(
        {"landslide": (0.6, RiskLevel.High), "flood": (0.5, RiskLevel.High)},
        rule=spenta,
    ) == pytest.approx(0.6)


def test_senza_pericoli_e_zero() -> None:
    assert attention_index({}, rule=_REGOLA) == 0.0


def test_at_or_above() -> None:
    assert at_or_above(RiskLevel.High, RiskLevel.Moderate)
    assert not at_or_above(RiskLevel.Low, RiskLevel.Moderate)
