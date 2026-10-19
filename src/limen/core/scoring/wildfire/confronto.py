"""La nostra catena FWI accanto a quella ufficiale (#280): solo numeri.

Puro: riceve coppie (nostro, riferimento) per componente e restituisce scarto
medio, errore assoluto e quadratico, correlazione, e per l'FWI l'accordo di
classe con le stesse bande che il motore usa (`wildfire.yaml`, cutoff di
classe sull'FWI normalizzato). Nessun I/O, nessun effetto sul punteggio.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from limen.core.models.risk import RiskLevel
from limen.core.scoring.base import classify_score
from limen.core.scoring.regional_thresholds import ClassCutoffs


@dataclass(frozen=True, slots=True)
class Esito:
    componente: str
    n: int
    #: Media di nostro meno riferimento: positivo vuol dire che sovrastimiamo.
    bias: float
    mae: float
    rmse: float
    #: Pearson; ``None`` con meno di tre coppie o varianza nulla.
    r: float | None
    #: Solo per l'FWI: quota di coppie nella stessa classe, e quota con il
    #: nostro sopra di almeno una classe (la direzione che allarma).
    stessa_classe: float | None = None
    sopra: float | None = None


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


_ORDINE = {
    RiskLevel.None_: 0,
    RiskLevel.Low: 1,
    RiskLevel.Moderate: 2,
    RiskLevel.High: 3,
    RiskLevel.VeryHigh: 4,
}


def classe_fwi(fwi: float, *, normalisation_max: float, cutoffs: ClassCutoffs) -> RiskLevel:
    """La classe dell'FWI normalizzato: quella che il motore darebbe a una cella in cui
    combustibile e pendenza sono al massimo (base + fuel + slope = 1)."""
    return classify_score(min(max(fwi, 0.0) / normalisation_max, 1.0), cutoffs)


def confronta(
    coppie: dict[str, list[tuple[float, float]]],
    *,
    normalisation_max: float,
    cutoffs: ClassCutoffs,
) -> list[Esito]:
    out: list[Esito] = []
    for componente, valori in coppie.items():
        if not valori:
            continue
        nostri = [a for a, _ in valori]
        rif = [b for _, b in valori]
        diff = [a - b for a, b in valori]
        n = len(valori)
        stessa = sopra = None
        if componente == "fwi":
            classi = [
                (
                    _ORDINE[classe_fwi(a, normalisation_max=normalisation_max, cutoffs=cutoffs)],
                    _ORDINE[classe_fwi(b, normalisation_max=normalisation_max, cutoffs=cutoffs)],
                )
                for a, b in valori
            ]
            stessa = sum(1 for a, b in classi if a == b) / n
            sopra = sum(1 for a, b in classi if a > b) / n
        out.append(
            Esito(
                componente=componente,
                n=n,
                bias=sum(diff) / n,
                mae=sum(abs(d) for d in diff) / n,
                rmse=math.sqrt(sum(d * d for d in diff) / n),
                r=_pearson(nostri, rif),
                stessa_classe=stessa,
                sopra=sopra,
            )
        )
    return out


__all__ = ["Esito", "classe_fwi", "confronta"]
