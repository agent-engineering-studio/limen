"""Il correttore multi-modello della pioggia (#155, punto 1): le parti pure.

Il 6 ottobre 2026 su Trieste i modelli davano fra 29 e 108 mm in 72 ore.
Questi test fissano come si costruiscono le finestre da confrontare e come si
misura un correttore — con il tasso di base accanto al tasso di successo.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from limen.cli.rain_ensemble import SOGLIA_MM, blocco, campioni, caratteristiche, punteggi
from limen.integrations.openmeteo.previous_runs import MODELLI

_NODO = (13.75, 45.75)
_D0 = date(2025, 10, 1)


def _giorni(n: int, mm: float) -> dict[date, float]:
    return {_D0 + timedelta(days=i): mm for i in range(n)}


def test_la_finestra_usa_gli_anticipi_uno_due_tre_e_somma_tre_giorni() -> None:
    previste = {
        (*_NODO, modello, lead): _giorni(5, 10.0 * lead)
        for modello in MODELLI[:3]
        for lead in (1, 2, 3)
    }
    osservate = {_NODO: _giorni(5, 5.0)}
    finestre = campioni(previste, osservate)
    # Cinque giorni osservati fanno tre finestre complete di tre giorni.
    assert [c.giorno for c in finestre] == [_D0 + timedelta(days=i) for i in range(3)]
    # Giorno 1 con anticipo 1, giorno 2 con anticipo 2, giorno 3 con 3.
    assert finestre[0].previsioni[MODELLI[0]] == 10.0 + 20.0 + 30.0
    assert finestre[0].osservata == 15.0


def test_con_meno_di_tre_modelli_la_finestra_non_entra() -> None:
    previste = {(*_NODO, m, lead): _giorni(3, 1.0) for m in MODELLI[:2] for lead in (1, 2, 3)}
    assert campioni(previste, {_NODO: _giorni(3, 1.0)}) == []


def test_un_modello_mancante_resta_un_buco_non_uno_zero() -> None:
    previste = {(*_NODO, m, lead): _giorni(3, 1.0) for m in MODELLI[:3] for lead in (1, 2, 3)}
    [finestra] = campioni(previste, {_NODO: _giorni(3, 1.0)})
    x = caratteristiche(finestra)
    assert math.isnan(x[MODELLI.index(MODELLI[4])])


def test_i_punteggi_dicono_anche_il_tasso_di_base() -> None:
    # Chi dice sempre «sopra soglia» prende ogni evento: il tasso di base e
    # i falsi allarmi sono ciò che lo smaschera.
    osservate = [0.0, 0.0, 0.0, 50.0]
    sempre = punteggi([SOGLIA_MM + 1] * 4, osservate)
    assert sempre["colpiti"] == 1.0
    assert sempre["tasso_base"] == 0.25
    assert sempre["falsi_allarmi"] == 0.75


def test_i_blocchi_sono_di_due_gradi() -> None:
    assert blocco(13.75, 45.75) == blocco(12.1, 44.1)
    assert blocco(13.75, 45.75) != blocco(14.1, 45.75)
