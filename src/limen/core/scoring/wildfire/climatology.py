"""Dove cade un FWI nella distribuzione del suo luogo e del suo mese.

Funzioni pure: niente database, niente rete. Le usa `limen fwi-climatology`
per riassumere anni di catena in 21 quantili, e l'API per dire a che
percentile cade il valore di oggi.
"""

from __future__ import annotations

from collections.abc import Sequence

#: I livelli dei quantili salvati: 0, 5, …, 100.
LIVELLI: tuple[float, ...] = tuple(5.0 * i for i in range(21))


def quantili(valori: Sequence[float]) -> list[float]:
    """I 21 quantili di ``valori``, con interpolazione lineare fra i ranghi."""
    if not valori:
        raise ValueError("servono valori per una distribuzione")
    ordinati = sorted(valori)
    n = len(ordinati)
    out: list[float] = []
    for livello in LIVELLI:
        pos = livello / 100.0 * (n - 1)
        basso = int(pos)
        alto = min(basso + 1, n - 1)
        frazione = pos - basso
        out.append(ordinati[basso] + (ordinati[alto] - ordinati[basso]) * frazione)
    return out


def percentile(valore: float, q: Sequence[float]) -> float:
    """A che percentile (0–100) cade ``valore`` fra i quantili ``q``.

    Interpolato fra i due quantili che lo racchiudono; fuori dalla
    distribuzione vale 0 o 100. Su un tratto piatto — molti giorni a FWI 0
    d'inverno — prende il centro del tratto, così un valore uguale a mezza
    distribuzione non si legge né come il minimo né come il massimo.
    """
    if len(q) != len(LIVELLI):
        raise ValueError(f"attesi {len(LIVELLI)} quantili, arrivati {len(q)}")
    if valore <= q[0]:
        uguali = [lv for lv, v in zip(LIVELLI, q, strict=True) if v == q[0]]
        return (uguali[0] + uguali[-1]) / 2 if valore == q[0] else 0.0
    if valore >= q[-1]:
        uguali = [lv for lv, v in zip(LIVELLI, q, strict=True) if v == q[-1]]
        return (uguali[0] + uguali[-1]) / 2 if valore == q[-1] else 100.0
    for i in range(1, len(q)):
        if valore < q[i]:
            basso, alto = q[i - 1], q[i]
            return LIVELLI[i - 1] + (valore - basso) / (alto - basso) * (
                LIVELLI[i] - LIVELLI[i - 1]
            )
        if valore == q[i]:
            uguali = [lv for lv, v in zip(LIVELLI, q, strict=True) if v == q[i]]
            return (uguali[0] + uguali[-1]) / 2
    return 100.0
