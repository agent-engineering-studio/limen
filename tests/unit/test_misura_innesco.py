"""Le letture di ``limen misura-innesco`` (#676)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
from rainfall_thresholds import PowerLawThreshold

from limen.cli.misura_innesco import (
    FINESTRE_122,
    TARATURA,
    Frana,
    fine_finestra_frana,
    finestre,
    istanti,
    lettura_caine,
    lettura_cumulata,
    massimo,
    nodo_piu_vicino,
    relativa,
)

_CURVA = PowerLawThreshold(alpha=7.0, beta=0.5)


def _caine(serie: np.ndarray, e: int, *, piu_forte: bool = False) -> float | None:
    return lettura_caine(serie, e, _CURVA, pausa_ore=6, minimo_mm=1.0, piu_forte=piu_forte)


def test_finestre_della_122() -> None:
    elenco = finestre(FINESTRE_122)
    assert len(elenco) == 12
    assert sum(f.taratura for f in elenco) == len(TARATURA) == 6
    assert {f.aoi_id for f in elenco if f.taratura} == TARATURA


def test_cumulata_somma_le_ultime_24_ore() -> None:
    serie = np.zeros(120)
    serie[70:80] = 2.0
    assert lettura_cumulata(serie, 79) == 20.0
    assert lettura_cumulata(serie, 90) == 20.0
    assert lettura_cumulata(serie, 110) == 0.0
    assert lettura_cumulata(serie, 10) is None


def test_un_ora_non_misurata_non_e_zero() -> None:
    serie = np.zeros(100)
    serie[60] = math.nan
    assert lettura_cumulata(serie, 70) is None
    assert _caine(serie, 70) is None


def test_caine_senza_pioggia_non_e_zero_ma_il_minimo() -> None:
    assert _caine(np.zeros(100), 80) == -99.0


def test_caine_sotto_la_curva_e_negativo() -> None:
    serie = np.zeros(100)
    serie[70:80] = 0.2
    eccesso = _caine(serie, 85)
    assert eccesso is not None and -99.0 < eccesso < 0


def test_caine_piu_forte_contro_ultimo() -> None:
    serie = np.zeros(100)
    serie[50:56] = 20.0  # nubifragio
    serie[80:82] = 1.5  # pioggerella dopo una pausa
    ultimo = _caine(serie, 90)
    forte = _caine(serie, 90, piu_forte=True)
    assert ultimo is not None and forte is not None
    assert forte > 0 > ultimo


def test_relativa() -> None:
    assert relativa(30.0, 60.0) == 0.5
    assert relativa(None, 60.0) is None
    assert relativa(30.0, None) is None
    assert relativa(30.0, 0.0) is None


def test_massimo_ignora_i_non_misurati() -> None:
    assert massimo([None, 1.0, 3.0]) == 3.0
    assert massimo([None, None]) is None


def test_nodo_piu_vicino() -> None:
    nodi = [(10.0, 40.0), (10.1, 40.0), (10.0, 40.1), (10.1, 40.1)]
    assert nodo_piu_vicino(nodi, [0, 1, 2, 3], 10.09, 40.04) == 1
    assert nodo_piu_vicino(nodi, [0, 2], 10.09, 40.04) == 0


def test_istanti_ogni_sei_ore() -> None:
    base = datetime(2019, 11, 1, tzinfo=UTC)
    ore = istanti(base, 48, base + timedelta(hours=3), base + timedelta(hours=30))
    assert [base + timedelta(hours=e) for e in ore] == [
        base + timedelta(hours=h) for h in (6, 12, 18, 24, 30)
    ]


def test_una_data_senza_ora_guarda_tutto_il_giorno() -> None:
    t = datetime(2019, 11, 24, tzinfo=UTC)

    def frana(precisione: str | None) -> Frana:
        return Frana("it-liguria", 8.9, 44.4, t, precisione, "P1")

    assert fine_finestra_frana(frana("T3")) == t + timedelta(hours=23)
    assert fine_finestra_frana(frana(None)) == t + timedelta(hours=23)
    assert fine_finestra_frana(frana("T1")) == t
    assert frana("T2").al_giorno and not frana("T3").al_giorno
