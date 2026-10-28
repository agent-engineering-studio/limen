"""La climatologia per nodo dell'innesco `cumulata` (#243)."""

from __future__ import annotations

import numpy as np
import pytest

from limen.cli.backtest import con_riferimento
from limen.cli.clima_pioggia import quantile_cumulata, riferimenti_aoi
from limen.core.models.risk import StaticFactors


def test_il_quantile_e_della_cumulata_non_dell_ora() -> None:
    anno = np.zeros(24 * 10)
    anno[100:124] = 2.0  # un giorno da 48 mm in 24 ore
    assert quantile_cumulata([anno], ore=24, quantile=1.0) == pytest.approx(48.0, abs=12.0)
    assert quantile_cumulata([anno], ore=1, quantile=1.0) == pytest.approx(2.0)


def test_la_finestra_non_scavalca_due_anni() -> None:
    fine = np.zeros(48)
    fine[-6:] = 4.0
    inizio = np.zeros(48)
    inizio[:6] = 4.0
    # Cumulati insieme farebbero 48 mm; anno per anno restano 24.
    assert quantile_cumulata([fine, inizio], ore=24, quantile=1.0) <= 24.0


def test_nodo_asciutto_o_vuoto_non_ha_riferimento() -> None:
    assert quantile_cumulata([np.zeros(24 * 30)], ore=24, quantile=0.999) is None
    assert quantile_cumulata([np.zeros(5)], ore=24, quantile=0.999) is None


def test_i_riferimenti_valgono_solo_per_la_stessa_finestra() -> None:
    clima = {"ore": 24, "quantile": 0.999, "aoi": {"it-x": [[16.0, 40.0, 50.0]]}}
    assert riferimenti_aoi(clima, "it-x", ore=24) == [(16.0, 40.0, 50.0)]
    assert riferimenti_aoi(clima, "it-x", ore=48) is None
    assert riferimenti_aoi(clima, "it-y", ore=24) is None


def test_ogni_cella_prende_il_nodo_piu_vicino() -> None:
    celle = [(StaticFactors(cell_id="a"), 16.01, 40.0), (StaticFactors(cell_id="b"), 16.09, 40.0)]
    out = con_riferimento(celle, [(16.0, 40.0, 30.0), (16.1, 40.0, None)])
    assert [sf.pioggia_riferimento_mm for sf, _, _ in out] == [30.0, None]
