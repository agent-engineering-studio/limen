"""La pioggia a 72 ore rispetto al clima del luogo.

Funzioni pure. `limen rain-climatology` riassume dieci anni di somme su tre
giorni in quantili per nodo; il motore dell'alluvione ne ricava soglia e
saturazione locali come i valori a due livelli fissi della distribuzione.
"""

from __future__ import annotations

from collections.abc import Sequence

#: I livelli dei quantili salvati, in frazione. Fitti in coda perché le soglie
#: stanno lì: 0,80 … 0,99 a passi di 0,01, poi 0,991 … 0,999 e il massimo.
LIVELLI: tuple[float, ...] = (
    *(round(0.80 + 0.01 * i, 3) for i in range(20)),
    *(round(0.991 + 0.001 * i, 3) for i in range(9)),
    1.0,
)


def somme_tre_giorni(giornaliere: Sequence[float]) -> list[float]:
    """Le somme mobili su tre giorni consecutivi."""
    return [sum(giornaliere[i : i + 3]) for i in range(len(giornaliere) - 2)]


def quantili(valori: Sequence[float]) -> list[float]:
    """I quantili di ``valori`` ai `LIVELLI`, interpolati fra i ranghi."""
    if not valori:
        raise ValueError("servono valori per una distribuzione")
    ordinati = sorted(valori)
    n = len(ordinati)
    out: list[float] = []
    for livello in LIVELLI:
        pos = livello * (n - 1)
        basso = int(pos)
        alto = min(basso + 1, n - 1)
        out.append(ordinati[basso] + (ordinati[alto] - ordinati[basso]) * (pos - basso))
    return out


def valore_al_livello(livello: float, q: Sequence[float]) -> float:
    """La pioggia che corrisponde a ``livello`` nella distribuzione ``q``."""
    if len(q) != len(LIVELLI):
        raise ValueError(f"attesi {len(LIVELLI)} quantili, arrivati {len(q)}")
    if livello <= LIVELLI[0]:
        return q[0]
    for i in range(1, len(LIVELLI)):
        if livello <= LIVELLI[i]:
            basso, alto = LIVELLI[i - 1], LIVELLI[i]
            return q[i - 1] + (q[i] - q[i - 1]) * (livello - basso) / (alto - basso)
    return q[-1]


def livello_del_valore(valore: float, q: Sequence[float]) -> float:
    """A che livello cade ``valore``: l'inversa di `valore_al_livello`.

    Sotto il primo quantile salvato restituisce il primo livello: la coda
    bassa non serve alle soglie e non è salvata.
    """
    if len(q) != len(LIVELLI):
        raise ValueError(f"attesi {len(LIVELLI)} quantili, arrivati {len(q)}")
    if valore <= q[0]:
        return LIVELLI[0]
    for i in range(1, len(q)):
        if valore <= q[i]:
            if q[i] == q[i - 1]:
                return LIVELLI[i]
            return LIVELLI[i - 1] + (LIVELLI[i] - LIVELLI[i - 1]) * (valore - q[i - 1]) / (
                q[i] - q[i - 1]
            )
    return 1.0
