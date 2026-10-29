"""Il truth set del backtest frane, filtrato per precisione e sorgente."""

from __future__ import annotations

import pytest

from limen.cli.backtest import PRECISIONI_LUOGO, descrivi_verita, precisioni_fino_a


@pytest.mark.parametrize(
    ("massima", "attese"),
    [("P0", ["P0"]), ("P1", ["P0", "P1"]), ("P10", ["P0", "P1", "P10"])],
)
def test_una_precisione_tiene_anche_quelle_piu_strette(massima: str, attese: list[str]) -> None:
    assert precisioni_fino_a(massima) == attese


def test_la_piu_larga_tiene_tutta_la_scala() -> None:
    assert precisioni_fino_a("P100") == list(PRECISIONI_LUOGO)


def test_il_report_dice_che_verita_ha_usato() -> None:
    assert descrivi_verita(None, None) == "ogni precisione; ogni sorgente"
    assert descrivi_verita(["P0", "P1"], ["stampa"]) == "precisione P1 o migliore; sorgenti stampa"


def test_senza_far_max_il_far_e_informazione_e_decide_la_discriminazione() -> None:
    from limen.cli.backtest import _righe_gate_far_e_discriminazione

    righe = _righe_gate_far_e_discriminazione(
        far=0.95, far_max=None, quota_allertate=0.05, discriminazione=2.7, discriminazione_min=2.0
    )
    assert "non è un gate" in righe[0]
    assert righe[1].endswith("**PASS**")
    fallita = _righe_gate_far_e_discriminazione(
        far=0.95, far_max=0.30, quota_allertate=0.53, discriminazione=1.2, discriminazione_min=2.0
    )
    assert fallita[0].endswith("**FAIL**")
    assert fallita[1].endswith("**FAIL**")


def test_a_parita_di_carico_si_accende_la_quota_chiesta_e_non_la_classe() -> None:
    from datetime import UTC, datetime, timedelta

    from limen.cli.backtest import colte_a_carico

    t0 = datetime(2019, 11, 1, tzinfo=UTC)
    frana = t0 + timedelta(hours=10)
    truth = {"a": frana, "b": frana}
    verita = {"a": [(t0, 0.6)], "b": [(t0, 0.2)]}
    massimi = [0.6, 0.2] + [0.1] * 8 + [0.0] * 10

    soglia, effettivo, colte = colte_a_carico(
        massimi, verita, truth, carico=0.05, lead_max_hours=72
    )
    assert (soglia, effettivo, colte) == (0.6, 0.05, 1)
    _, effettivo, colte = colte_a_carico(massimi, verita, truth, carico=0.10, lead_max_hours=72)
    assert (effettivo, colte) == (0.10, 2)
    # Le celle a zero non si accendono: chiedere il 90 % ne accende il 50 %.
    soglia, effettivo, _ = colte_a_carico(massimi, verita, truth, carico=0.9, lead_max_hours=72)
    assert (soglia, effettivo) == (0.1, 0.5)


def test_per_comune_conta_comuni_giorno_e_la_finestra_di_72_ore() -> None:
    from datetime import UTC, datetime, timedelta

    from limen.cli.backtest import per_comune

    # Quattro giorni orari; il giorno si legge in ora italiana.
    ore = [datetime(2019, 11, 1, tzinfo=UTC) + timedelta(hours=h) for h in range(96)]
    frana = ore[90]
    orario = {
        # Moderato solo 100 ore prima: fuori dalla finestra di 72.
        "fuori": [0.5 if h == 0 else 0.0 for h in range(96)],
        # Moderato 20 ore prima.
        "dentro": [0.4 if h == 70 else 0.0 for h in range(96)],
        **{f"calmo{k}": [0.1] * 96 for k in range(8)},
    }
    verita = {"fuori": ore[95] + timedelta(hours=10), "dentro": frana}
    c = per_comune(orario, ore, verita, soglia_classe=0.35, finestra_ore=72, carico=0.10)
    assert (c.eventi, c.colti_classe) == (2, 1)
    # Due comuni-giorno ≥ Moderato su dieci comuni per cinque giorni italiani
    # (le 96 ore UTC toccano il 1°-5 novembre a Roma).
    assert c.carico_classe == pytest.approx(2 / 50)
    # Il 10 % dei comuni-giorno accende anche i calmi a 0,1, ma «fuori» resta
    # mancato: è sopra soglia solo prima della finestra.
    assert c.soglia_carico == 0.1
    assert c.colti_carico == 1
    # Un comune senza celle nel backtest non è un evento colto.
    vuoto = per_comune({}, ore, {"x": frana}, soglia_classe=0.35, finestra_ore=72, carico=0.1)
    assert (vuoto.eventi, vuoto.colti_carico) == (1, 0)


def test_il_report_per_comune_dice_il_traguardo() -> None:
    from limen.cli.backtest import PerComune, _righe_comuni
    from limen.core.scoring.regional_thresholds import MetricaComuni

    metro = MetricaComuni(finestra_ore=72, carico_massimo=0.10, obiettivo=0.90)
    righe = _righe_comuni(PerComune(10, 4, 0.3, 0.52, 9, 0.1), metro)
    assert any("90.00% (9)" in r and r.endswith("**PASS**") for r in righe)
    righe = _righe_comuni(PerComune(10, 4, 0.3, 0.52, 3, 0.1), metro)
    assert righe[-2].endswith("**FAIL**")
    # Colto tutto, ma con tutti i comuni-giorno accesi a pari merito: FAIL.
    righe = _righe_comuni(PerComune(10, 10, 1.0, 0.5, 10, 1.0), metro)
    assert righe[-2].endswith("**FAIL**")
