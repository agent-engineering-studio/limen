"""Governo degli alert: rollup comunale, rate limiting, digest (issue #59).

Tre pericoli su ~312.000 celle: un fronte temporalesco esteso porta migliaia
di celle sopra soglia nello stesso ciclo. Il destinatario però non è un
sistema, è una persona in un centro operativo comunale — e a lei non serve
sapere *quali* celle, serve sapere *quali comuni* e *quanto è grave*.

Qui dentro c'è solo la parte decidibile senza I/O, così è provabile
direttamente: raggruppare per comune, scegliere se spedire o accodare, e
scrivere le frasi italiane. Le letture (quante uscite nell'ultima ora, quali
comuni già allertati) e le scritture stanno nel repo; il dispatch sta
nell'executor.

Due scelte che il resto del modulo dà per fatte:

* **Il comune è l'unità dell'alert, la cella resta nel dettaglio.** Un
  messaggio per comune con il conteggio delle celle e le peggiori tre; le
  celle restano consultabili nel payload e nel breakdown. Mandare N messaggi
  per N celle dello stesso paese non aggiunge informazione, consuma
  attenzione.
* **La classe massima non aspetta.** Il digest è una risposta al volume, non
  alla gravità: una cella VeryHigh esce subito anche a limite superato. Un
  rate limit che ritarda l'allerta peggiore ha invertito il proprio scopo.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from limen.core.models.context import CellRiskRecord
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel

#: Ordine delle classi. Non alfabetico: 'VeryHigh' verrebbe dopo 'None'.
_LEVEL_RANK: dict[RiskLevel, int] = {
    RiskLevel.None_: 0,
    RiskLevel.Low: 1,
    RiskLevel.Moderate: 2,
    RiskLevel.High: 3,
    RiskLevel.VeryHigh: 4,
}

_LEVEL_LABEL_IT: dict[RiskLevel, str] = {
    RiskLevel.None_: "nessuno",
    RiskLevel.Low: "basso",
    RiskLevel.Moderate: "moderato",
    RiskLevel.High: "alto",
    RiskLevel.VeryHigh: "molto alto",
}

_HAZARD_LABEL_IT: dict[HazardType, str] = {
    HazardType.LANDSLIDE: "frana",
    HazardType.FLOOD: "alluvione",
    HazardType.WILDFIRE: "incendio",
}

#: Celle nominate per comune. Tre: abbastanza per orientarsi sul territorio,
#: poche perché un elenco più lungo di così non lo legge nessuno.
CELLS_PER_COMUNE = 3

#: Etichetta dei comuni non ancora taggati (`cell_comune` vuota per la cella).
#: Un nome, non `None` sparso nelle frasi: quelle celle esistono e vanno
#: nominate, e "fuori dai confini comunali noti" è il fatto.
UNKNOWN_COMUNE_LABEL = "area non attribuita"


@dataclass(frozen=True, slots=True)
class ComuneAggregate:
    """Le celle sopra soglia di un comune, per un pericolo, in un ciclo."""

    istat_code: str | None
    comune: str | None
    aoi_id: str
    hazard: HazardType
    max_level: RiskLevel
    max_score: float
    cells_count: int
    #: Le peggiori per priorità, non per punteggio: è l'ordine con cui
    #: l'executor le ha già disposte, e tiene conto dell'esposizione.
    top_cells: tuple[tuple[str, float, RiskLevel], ...]

    @property
    def label(self) -> str:
        return self.comune or UNKNOWN_COMUNE_LABEL


def aggregate_by_comune(
    prioritised: Sequence[tuple[CellRiskRecord, float]],
    *,
    comuni: dict[str, str],
    istat_codes: dict[str, str],
    aoi_id: str,
    hazard: HazardType,
    cells_per_comune: int = CELLS_PER_COMUNE,
) -> list[ComuneAggregate]:
    """Raggruppa le celle già ordinate per priorità nei loro comuni.

    L'ordine in uscita è per gravità: prima la classe massima, poi il
    punteggio massimo, poi il nome. Deterministico anche a parità, perché due
    esecuzioni sugli stessi dati devono produrre lo stesso messaggio.
    """
    per_comune: dict[str | None, list[tuple[CellRiskRecord, float]]] = {}
    for record, priority in prioritised:
        key = istat_codes.get(record.cell_id)
        per_comune.setdefault(key, []).append((record, priority))

    out: list[ComuneAggregate] = []
    for code, items in per_comune.items():
        worst = max(items, key=lambda it: (_LEVEL_RANK[it[0].level], it[0].score))[0]
        out.append(
            ComuneAggregate(
                istat_code=code,
                comune=comuni.get(code) if code else None,
                aoi_id=aoi_id,
                hazard=hazard,
                max_level=worst.level,
                max_score=worst.score,
                cells_count=len(items),
                top_cells=tuple((r.cell_id, r.score, r.level) for r, _ in items[:cells_per_comune]),
            )
        )
    out.sort(key=lambda a: (-_LEVEL_RANK[a.max_level], -a.max_score, a.label))
    return out


def worst_level(aggregates: Iterable[ComuneAggregate]) -> RiskLevel:
    """La classe peggiore fra gli aggregati. ``None_`` se non ce ne sono."""
    levels = [a.max_level for a in aggregates]
    if not levels:
        return RiskLevel.None_
    return max(levels, key=lambda lv: _LEVEL_RANK[lv])


Verdict = Literal["send", "queue"]


def rate_limit_verdict(
    *,
    sends_last_hour: int,
    max_per_hour: int,
    level: RiskLevel,
    bypass_level: RiskLevel,
    enabled: bool = True,
) -> Verdict:
    """Spedire subito o accodare nel digest.

    ``bypass_level`` è la soglia oltre la quale il volume non conta più: il
    digest serve a proteggere l'attenzione, e trattenere l'allerta peggiore
    per proteggere l'attenzione è esattamente il contrario di quel che serve.

    Con ``max_per_hour <= 0`` il limite è disattivato: zero significherebbe
    "non spedire mai", che nessun operatore intende scrivendo 0.
    """
    if not enabled or max_per_hour <= 0:
        return "send"
    if _LEVEL_RANK[level] >= _LEVEL_RANK[bypass_level]:
        return "send"
    return "queue" if sends_last_hour >= max_per_hour else "send"


def summarise_comuni_it(
    aggregates: Sequence[ComuneAggregate],
    *,
    max_comuni: int = 5,
) -> str:
    """Frase italiana del rollup comunale, per un solo pericolo.

    Solo numeri già negli aggregati: nessun LLM nel percorso degli alert.
    """
    if not aggregates:
        return ""
    hazard = aggregates[0].hazard
    etichetta = _HAZARD_LABEL_IT.get(hazard, hazard.value)
    livello = _LEVEL_LABEL_IT[worst_level(aggregates)]
    celle = sum(a.cells_count for a in aggregates)

    testa = aggregates[:max_comuni]
    dove = "; ".join(
        f"{a.label}: {a.cells_count} "
        f"{'area' if a.cells_count == 1 else 'aree'} "
        f"(max {a.max_score:.2f})"
        for a in testa
    )
    resto = len(aggregates) - len(testa)
    if resto > 0:
        dove += f"; e altri {resto} comuni"

    return (
        f"Rischio {etichetta}, livello {livello}: "
        f"{celle} {'area' if celle == 1 else 'aree'} da 1 km² "
        f"in {len(aggregates)} {'comune' if len(aggregates) == 1 else 'comuni'}. "
        f"{dove}."
    )


def summarise_digest_it(
    aggregates: Sequence[ComuneAggregate],
    *,
    max_comuni: int = 10,
) -> str:
    """Testo del digest: un messaggio, tutti i pericoli, raggruppati per comune.

    È anche il punto in cui l'**alert congiunto** della #58 diventa reale. Il
    workflow è per pericolo, quindi due pericoli sopra soglia sulla stessa
    cella nascono in due esecuzioni separate che non si conoscono; la coda del
    digest le ritrova insieme, e un comune con frana e alluvione insieme
    riceve una riga che le nomina entrambe invece di due messaggi che sembrano
    eventi distinti.
    """
    if not aggregates:
        return ""

    per_comune: dict[str, list[ComuneAggregate]] = {}
    for a in aggregates:
        per_comune.setdefault(a.label, []).append(a)

    ordinati = sorted(
        per_comune.items(),
        key=lambda kv: (-_LEVEL_RANK[worst_level(kv[1])], -max(a.max_score for a in kv[1]), kv[0]),
    )

    righe: list[str] = []
    for label, gruppo in ordinati[:max_comuni]:
        pericoli = ", ".join(
            f"{_HAZARD_LABEL_IT.get(a.hazard, a.hazard.value)} "
            f"{_LEVEL_LABEL_IT[a.max_level]} ({a.cells_count})"
            for a in sorted(gruppo, key=lambda x: (-_LEVEL_RANK[x.max_level], x.hazard.value))
        )
        # Due o più pericoli nello stesso comune: è il fatto che un messaggio
        # per pericolo non riuscirebbe a dire.
        marca = " ⚠ più pericoli insieme" if len(gruppo) > 1 else ""
        righe.append(f"· {label}: {pericoli}{marca}")

    resto = len(ordinati) - len(righe)
    celle = sum(a.cells_count for a in aggregates)
    intestazione = (
        f"Riepilogo allerte: {celle} {'area' if celle == 1 else 'aree'} da 1 km² "
        f"in {len(ordinati)} {'comune' if len(ordinati) == 1 else 'comuni'}, "
        f"livello massimo {_LEVEL_LABEL_IT[worst_level(aggregates)]}."
    )
    coda = f"\n· e altri {resto} comuni." if resto > 0 else ""
    return intestazione + "\n" + "\n".join(righe) + coda


__all__ = [
    "CELLS_PER_COMUNE",
    "UNKNOWN_COMUNE_LABEL",
    "ComuneAggregate",
    "Verdict",
    "aggregate_by_comune",
    "rate_limit_verdict",
    "summarise_comuni_it",
    "summarise_digest_it",
    "worst_level",
]
