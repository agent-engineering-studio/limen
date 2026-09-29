"""I tre pericoli di un comune diventano un numero solo.

La colonna della dashboard mostra i pericoli affiancati — ognuno con il suo
punteggio e la sua classe — e accanto un numero che dice quali comuni
guardare per primi. Questo modulo è quel numero, ed è una funzione pura:
nessun accesso al database, nessuna soglia scritta qui dentro.
"""

from __future__ import annotations

from collections.abc import Mapping

from limen.core.cascades.config import AttentionRule
from limen.core.models.risk import RiskLevel

#: Ordine delle classi, per confrontare una soglia con una classe.
_ORDINE: tuple[RiskLevel, ...] = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)


def at_or_above(level: RiskLevel, floor: RiskLevel) -> bool:
    return _ORDINE.index(level) >= _ORDINE.index(floor)


def attention_index(
    per_hazard: Mapping[str, tuple[float, RiskLevel]],
    *,
    rule: AttentionRule,
) -> float:
    """Un numero per comune, dai pericoli che lo riguardano.

    `per_hazard` associa a ogni pericolo la sua **priorità** — cioè
    `punteggio per uno piu l'esposizione`, la stessa che il dispacciatore degli
    alert usa da sempre — e la sua classe.

    Il risultato è il massimo di quelle priorità, aumentato quando i pericoli
    oltre soglia sono più di uno. Non è una somma, e la ragione si vede con
    due numeri: sommando, un comune con tre pericoli a 0,40 (totale 1,20)
    passerebbe davanti a uno con un versante a 0,80, che è l'unico dei due
    dove sta per succedere qualcosa.

    Senza pericoli, o con la regola spenta, resta il massimo — mai zero per
    convenzione: un comune senza dati non è un comune tranquillo, e chi
    legge la lista lo vede dalla classe, non da questo numero.
    """
    if not per_hazard:
        return 0.0
    massimo = max(priorita for priorita, _ in per_hazard.values())
    if not rule.enabled or rule.multi_hazard_bump <= 0.0:
        return massimo
    oltre = sum(1 for _, level in per_hazard.values() if at_or_above(level, rule.min_level))
    if oltre < 2:
        return massimo
    return massimo * (1.0 + rule.multi_hazard_bump * (oltre - 1))
