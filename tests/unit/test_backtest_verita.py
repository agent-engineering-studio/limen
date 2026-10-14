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
