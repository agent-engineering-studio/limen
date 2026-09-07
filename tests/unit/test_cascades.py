"""Regole di cascata fra pericoli (issue #58).

Sono le due che l'issue chiede di testare unitariamente: l'amplificazione
pluviale post-incendio e l'alert congiunto da pioggia estrema.

Il criterio di accettazione «nessuna regola cablata nel codice» si verifica
qui in modo diretto: ogni numero arriva dalla configurazione, e i test lo
provano sostituendola invece di riscrivere il codice.
"""

from __future__ import annotations

import datetime as dt

import pytest

from limen.core.cascades import load_cascades
from limen.core.cascades.config import CascadeRules, JointRainRule, PostFireFloodRule
from limen.core.cascades.rules import joint_rain_cells, post_fire_flood_multiplier
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel

NOW = dt.datetime(2026, 11, 3, 12, tzinfo=dt.UTC)


def _rules() -> CascadeRules:
    return load_cascades()


# ---------------------------------------------------------------------------
# Incendio → alluvione
# ---------------------------------------------------------------------------
def test_no_recent_fire_means_no_amplification() -> None:
    """Assente non è "molto vecchio", ma entrambi valgono 1.0: la cascata non
    deve inventare un effetto dove non c'è un incendio."""
    rule = _rules().post_fire_flood
    assert post_fire_flood_multiplier(None, rule=rule) == 1.0
    assert post_fire_flood_multiplier(rule.window_months + 1, rule=rule) == 1.0
    assert post_fire_flood_multiplier(-1.0, rule=rule) == 1.0


def test_the_amplification_peaks_after_a_few_months_not_immediately() -> None:
    """L'effetto richiede che la pioggia trovi la crosta idrofobica intatta e
    la vegetazione non ancora ricresciuta: massimo al picco, non al giorno
    dopo l'incendio."""
    rule = _rules().post_fire_flood
    subito = post_fire_flood_multiplier(0.0, rule=rule)
    picco = post_fire_flood_multiplier(rule.peak_months, rule=rule)
    tardi = post_fire_flood_multiplier(rule.window_months - 0.1, rule=rule)

    assert picco == pytest.approx(rule.max_multiplier)
    assert 1.0 < subito < picco
    assert 1.0 < tardi < picco


def test_the_amplification_never_leaves_its_declared_range() -> None:
    """Un moltiplicatore sotto 1 ridurrebbe il rischio dopo un incendio, sopra
    il massimo lo gonfierebbe oltre quanto dichiarato: entrambi renderebbero
    il punteggio non spiegabile."""
    rule = _rules().post_fire_flood
    for m in [x / 4 for x in range(0, int(rule.window_months * 4) + 8)]:
        got = post_fire_flood_multiplier(float(m), rule=rule)
        assert 1.0 <= got <= rule.max_multiplier, m


def test_a_disabled_rule_is_inert() -> None:
    """Spegnere una cascata deve riportare esattamente al comportamento senza
    cascata, non a un effetto ridotto."""
    rule = _rules().post_fire_flood.model_copy(update={"enabled": False})
    assert post_fire_flood_multiplier(rule.peak_months, rule=rule) == 1.0


def test_the_numbers_come_from_configuration_not_from_code() -> None:
    """Il criterio «niente cablato»: cambiando solo la configurazione cambia
    il risultato, senza toccare una riga di codice."""
    base = _rules().post_fire_flood
    doppio = base.model_copy(update={"max_multiplier": 2.2})
    assert post_fire_flood_multiplier(base.peak_months, rule=doppio) == pytest.approx(2.2)


def test_a_peak_outside_the_window_is_refused() -> None:
    """Un picco fuori finestra darebbe un'amplificazione che non raggiunge mai
    il massimo dichiarato: la configurazione mentirebbe sul proprio effetto."""
    with pytest.raises(ValueError, match="cade fuori dalla finestra"):
        PostFireFloodRule.model_validate(
            {
                "enabled": True,
                "window_months": 6.0,
                "peak_months": 10.0,
                "curve_denominator": 40.0,
                "max_multiplier": 1.5,
            }
        )


# ---------------------------------------------------------------------------
# Pioggia estrema → alert congiunto
# ---------------------------------------------------------------------------
def _cells(
    **kwargs: tuple[RiskLevel, float, dt.datetime],
) -> dict[str, tuple[RiskLevel, float, dt.datetime]]:
    return dict(kwargs)


def test_one_hazard_alone_is_not_a_joint_alert() -> None:
    """Serve che almeno due pericoli portino la stessa cella oltre soglia:
    un pericolo solo è già coperto dal suo alert."""
    rule = _rules().joint_rain
    got = joint_rain_cells(
        {HazardType.LANDSLIDE: {"c1": (RiskLevel.VeryHigh, 0.9, NOW)}},
        rule=rule,
        now=NOW,
    )
    assert got == []


def test_two_hazards_on_the_same_cell_produce_one_entry() -> None:
    """Il punto dell'issue: un messaggio con due rischi, non due messaggi."""
    rule = _rules().joint_rain
    got = joint_rain_cells(
        {
            HazardType.LANDSLIDE: {"c1": (RiskLevel.High, 0.6, NOW)},
            HazardType.FLOOD: {"c1": (RiskLevel.VeryHigh, 0.8, NOW)},
        },
        rule=rule,
        now=NOW,
    )
    assert len(got) == 1
    assert got[0].cell_id == "c1"
    assert got[0].hazards == (HazardType.FLOOD, HazardType.LANDSLIDE)
    assert got[0].worst_score == 0.8


def test_a_stale_assessment_does_not_count_as_simultaneous() -> None:
    """Gli sweep dei pericoli girano in momenti diversi.

    Senza la finestra, la lettura di ieri di un pericolo si combinerebbe con
    quella di adesso dell'altro e produrrebbe un allarme congiunto che non è
    mai esistito in nessun istante.
    """
    rule = _rules().joint_rain
    vecchio = NOW - dt.timedelta(hours=rule.window_hours + 1)
    got = joint_rain_cells(
        {
            HazardType.LANDSLIDE: {"c1": (RiskLevel.High, 0.6, vecchio)},
            HazardType.FLOOD: {"c1": (RiskLevel.High, 0.7, NOW)},
        },
        rule=rule,
        now=NOW,
    )
    assert got == []


def test_below_the_threshold_no_cell_qualifies() -> None:
    rule = _rules().joint_rain
    got = joint_rain_cells(
        {
            HazardType.LANDSLIDE: {"c1": (RiskLevel.Moderate, 0.4, NOW)},
            HazardType.FLOOD: {"c1": (RiskLevel.Moderate, 0.4, NOW)},
        },
        rule=rule,
        now=NOW,
    )
    assert got == []


def test_the_order_is_stable_across_runs() -> None:
    """La lista finisce in un messaggio: un ordine instabile la farebbe
    sembrare cambiata a ogni ciclo anche a parità di dati."""
    rule = _rules().joint_rain
    per_hazard = {
        HazardType.LANDSLIDE: {
            "b": (RiskLevel.High, 0.5, NOW),
            "a": (RiskLevel.High, 0.5, NOW),
            "c": (RiskLevel.VeryHigh, 0.9, NOW),
        },
        HazardType.FLOOD: {
            "b": (RiskLevel.High, 0.5, NOW),
            "a": (RiskLevel.High, 0.5, NOW),
            "c": (RiskLevel.High, 0.6, NOW),
        },
    }
    prima = [j.cell_id for j in joint_rain_cells(per_hazard, rule=rule, now=NOW)]
    dopo = [j.cell_id for j in joint_rain_cells(per_hazard, rule=rule, now=NOW)]
    assert prima == dopo
    # Peggiore per punteggio in testa, cell_id a spareggio.
    assert prima == ["c", "a", "b"]


def test_a_disabled_joint_rule_emits_nothing() -> None:
    rule = JointRainRule(enabled=False, min_level=RiskLevel.High, window_hours=6.0)
    got = joint_rain_cells(
        {
            HazardType.LANDSLIDE: {"c1": (RiskLevel.VeryHigh, 0.9, NOW)},
            HazardType.FLOOD: {"c1": (RiskLevel.VeryHigh, 0.9, NOW)},
        },
        rule=rule,
        now=NOW,
    )
    assert got == []


def test_three_hazards_on_one_cell_stay_one_entry() -> None:
    """Una cella non produce tre messaggi né tre voci: resta una, con l'elenco
    dei pericoli coinvolti."""
    rule = _rules().joint_rain
    got = joint_rain_cells(
        {
            HazardType.LANDSLIDE: {"c1": (RiskLevel.High, 0.6, NOW)},
            HazardType.FLOOD: {"c1": (RiskLevel.High, 0.7, NOW)},
            HazardType.WILDFIRE: {"c1": (RiskLevel.VeryHigh, 0.8, NOW)},
        },
        rule=rule,
        now=NOW,
    )
    assert len(got) == 1
    assert len(got[0].hazards) == 3
