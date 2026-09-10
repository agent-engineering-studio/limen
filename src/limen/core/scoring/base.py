"""Scoring-engine Protocol (V1 + V2 share this surface).

Both :class:`MultiFactorScoringEngine` (V1 deterministic) and
:class:`MLScoringEngine` (V2) satisfy this Protocol — anything the
workflow holds is typed against it, never the concrete class. That's
what makes the V2 engine a true drop-in: switching
``SCORING__ENGINE=ml`` doesn't ripple through the workflow.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from limen.core.models.risk import BreakdownT_co, CellFeatureBundle, RiskLevel, RiskScore

if TYPE_CHECKING:
    from limen.core.scoring.regional_thresholds import ClassCutoffs


def classify_score(score: float, cutoffs: ClassCutoffs) -> RiskLevel:
    """Map a score in [0, 1] onto the five classes.

    Hazard-agnostic on purpose: every engine produces the same unit scale and
    reads its own cutoffs from its own YAML, so the boundary logic is shared
    even though not a single number is.
    """
    if score < cutoffs.low.lo:
        return RiskLevel.None_
    if score < cutoffs.moderate.lo:
        return RiskLevel.Low
    if score < cutoffs.high.lo:
        return RiskLevel.Moderate
    if score < cutoffs.very_high.lo:
        return RiskLevel.High
    return RiskLevel.VeryHigh


@runtime_checkable
class ScoringEngine(Protocol[BreakdownT_co]):
    """Pure ``bundle → RiskScore`` mapping. No I/O. No network. No LLM.

    Parameterised by the hazard's breakdown shape. A consumer that reads the
    landslide components asks for ``ScoringEngine[ComponentBreakdown]`` and
    keeps full typing; the engine registry, which holds engines for several
    hazards, asks for ``ScoringEngine[HazardBreakdown]`` and sees only the
    discriminator. The parameter is covariant, so the first is assignable to
    the second.
    """

    def score(self, bundle: CellFeatureBundle) -> RiskScore[BreakdownT_co]: ...

    def score_many(
        self, bundles: Sequence[CellFeatureBundle]
    ) -> Sequence[RiskScore[BreakdownT_co]]:
        """Score a batch. Deve dare gli **stessi** numeri di ``score`` uno a uno.

        Esiste perché per un motore vettoriale la differenza non è di
        efficienza ma di ordine di grandezza: LightGBM predice 60.000 righe in
        una chiamata in meno di un secondo, e chiamato una riga alla volta paga
        60.000 volte l'attraversamento del confine Python/C.

        Per il V1 deterministico è il ciclo, e va bene così: misurato, 10.353
        celle costano 0,86 s, cioè 83 µs a cella in Python puro. Un motore che
        non ha niente da vettorizzare non deve fingere di averlo — ma deve
        offrire la stessa superficie, altrimenti il chiamante torna a
        distinguere i due casi e la sostituibilità del Protocol si perde.

        Ritorna una ``Sequence`` e non una ``list``: ``list`` è invariante nel
        suo parametro, quindi ``list[RiskScore[BreakdownT_co]]`` metterebbe una
        variabile covariante in posizione invariante e romperebbe la varianza
        del Protocol — quella che permette a ``RiskScore[ComponentBreakdown]``
        di passare dove si attende ``RiskScore[HazardBreakdown]``. Una lista
        resta un ritorno valido; è il *tipo dichiarato* a dover essere
        covariante.
        """
        return [self.score(b) for b in bundles]


__all__ = ["ScoringEngine", "classify_score"]
