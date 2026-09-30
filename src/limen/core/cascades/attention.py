"""I tre pericoli di un comune diventano un numero solo.

La colonna della dashboard mostra i pericoli affiancati — ognuno con il suo
punteggio e la sua classe — e accanto un numero che dice quali comuni
guardare per primi. Questo modulo è quel numero, ed è una funzione pura:
nessun accesso al database, nessuna soglia scritta qui dentro.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

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


class HazardStanding(NamedTuple):
    """Come sta un pericolo su un comune, per comporre il numero unico."""

    #: `punteggio per uno piu l'esposizione`, la stessa formula degli alert.
    priority: float
    level: RiskLevel
    #: Falso quando il segnale dinamico non è arrivato (#143). Un pericolo
    #: non misurato vale zero *per costruzione*, e quello zero non è una
    #: buona notizia da mettere in media con le altre.
    measured: bool = True


def attention_index(
    per_hazard: Mapping[str, HazardStanding],
    *,
    rule: AttentionRule,
) -> float | None:
    """Un numero per comune, dai pericoli che lo riguardano.

    Il risultato è il massimo delle priorità, aumentato quando i pericoli
    oltre soglia sono più di uno. Non è una somma, e la ragione si vede con
    due numeri: sommando, un comune con tre pericoli a 0,40 (totale 1,20)
    passerebbe davanti a uno con un versante a 0,80, che è l'unico dei due
    dove sta per succedere qualcosa.

    **I pericoli non misurati restano fuori**, dal massimo e dal conteggio.
    Un incendio senza catena FWI vale zero per costruzione: contarlo come
    «sotto soglia» abbassa il comune due volte, una perché non alza il
    massimo e una perché non conta come pericolo concomitante. E il secondo
    effetto è il peggiore — due pericoli su tre misurati e concomitanti
    perderebbero l'incremento per colpa del terzo, di cui non sappiamo
    niente.

    ``None`` quando non c'è **niente** di misurato: è l'unica risposta vera,
    e chi la mostra deve dire «non misurato», non «zero».
    """
    noti = {h: s for h, s in per_hazard.items() if s.measured}
    if not noti:
        return None
    massimo = max(s.priority for s in noti.values())
    if not rule.enabled or rule.multi_hazard_bump <= 0.0:
        return massimo
    oltre = sum(1 for s in noti.values() if at_or_above(s.level, rule.min_level))
    if oltre < 2:
        return massimo
    return massimo * (1.0 + rule.multi_hazard_bump * (oltre - 1))
