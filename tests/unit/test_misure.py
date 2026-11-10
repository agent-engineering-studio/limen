"""Misure offline (#480): AUC, stratificazione, osservate/attese su dati sintetici."""

from __future__ import annotations

import numpy as np
import pytest

from limen.cli.misura import anni
from limen.ml.misure import (
    Campione,
    auc,
    auc_stratificata,
    osservate_attese,
    soglie_quantili,
    strato,
)


def _c(valori: list[float], positive: list[bool], strati: list[str]) -> Campione:
    return Campione(np.array(valori, dtype=float), np.array(positive), np.array(strati))


def test_auc_perfetta_casuale_e_con_i_pari() -> None:
    assert auc(np.array([1.0, 2, 3, 4]), np.array([False, False, True, True])) == 1.0
    assert auc(np.array([1.0, 2, 3, 4]), np.array([True, True, False, False])) == 0.0
    # Tutti pari: ogni coppia vale mezza.
    assert auc(np.array([5.0, 5, 5, 5]), np.array([True, False, True, False])) == 0.5
    assert auc(np.array([1.0, 2]), np.array([True, True])) is None


def test_auc_coincide_con_il_conto_delle_coppie() -> None:
    rng = np.random.default_rng(7)
    v = rng.integers(0, 5, 200).astype(float)
    p = rng.random(200) < 0.3
    pos, neg = v[p], v[~p]
    coppie = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / (len(pos) * len(neg))
    assert auc(v, p) == pytest.approx(coppie)


def test_lo_strato_toglie_il_confondente() -> None:
    # Nello strato «caldo» tutto è più alto e brucia di più: sull'insieme la
    # feature sembra distinguere, dentro ogni strato non distingue.
    rng = np.random.default_rng(1)
    n = 400
    caldo = np.arange(n) < n // 2
    valori = np.where(caldo, 10.0, 0.0) + rng.random(n)
    positive = rng.random(n) < np.where(caldo, 0.5, 0.05)
    strati = np.where(caldo, "caldo", "freddo")
    c = Campione(valori, positive, strati)
    insieme = auc(valori, positive)
    assert insieme is not None
    assert insieme > 0.75
    a, usati = auc_stratificata(c)
    assert usati == 2
    assert a == pytest.approx(0.5, abs=0.1)


def test_uno_strato_senza_positive_non_conta() -> None:
    c = _c([1, 2, 3, 4, 9, 9], [False, True, False, True, False, False], ["a"] * 4 + ["b"] * 2)
    a, usati = auc_stratificata(c)
    assert usati == 1
    assert a == auc(np.array([1.0, 2, 3, 4]), np.array([False, True, False, True]))


def test_osservate_attese_dal_tasso_dello_strato() -> None:
    c = _c(
        [0, 0, 1, 1, 0, 1],
        [False, False, True, True, False, False],
        ["a", "a", "a", "a", "b", "b"],
    )
    righe = osservate_attese(c, np.array([0.5]))
    assert [(r.celle, r.osservate) for r in righe] == [(3, 0), (3, 2)]
    # Attese: strato a al 50 % (4 celle), strato b allo 0 %.
    assert [r.attese for r in righe] == [1.0, 1.0]
    assert righe[1].rapporto == 2.0
    assert righe[0].rapporto == 0.0


def test_soglie_da_quantili_senza_doppi() -> None:
    molti_zeri = soglie_quantili(np.array([0.0] * 80 + [1.0, 2, 3, 4] * 5), 5)
    assert len(molti_zeri) < 4
    assert list(molti_zeri) == sorted(set(molti_zeri))
    assert len(soglie_quantili(np.arange(100, dtype=float), 5)) == 4


def test_strato_nodo_e_fascia() -> None:
    assert strato(16.1, 40.6, 150.0, passo=0.25, fasce=(200.0, 500.0)) == "64:162:0"
    assert strato(16.1, 40.6, 650.0, passo=0.25, fasce=(200.0, 500.0)) == "64:162:2"
    assert strato(16.1, 40.6, None, passo=0.25, fasce=(200.0, 500.0)) == "64:162:?"


def test_anni() -> None:
    assert [d.isoformat() for d in anni("2021-2023")] == ["2021-01-01", "2023-12-31"]
    assert anni("2024")[1].isoformat() == "2024-12-31"
    with pytest.raises(ValueError):
        anni("2024-2021")
