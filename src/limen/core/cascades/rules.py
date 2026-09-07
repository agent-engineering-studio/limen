"""Le regole di cascata, come funzioni pure (#58).

Nessuna delle due decide da sé: prendono la configurazione come argomento e
non leggono né database né orologio. È la stessa disciplina dei motori di
scoring, per la stessa ragione — una cascata che dipendesse dall'ambiente non
sarebbe riproducibile in un backtest.

Il differenziatore di Limen rispetto a un sistema mono-rischio sta qui: le
interazioni fra pericoli. Ma sono interazioni *asimmetriche* e vanno lette
come tali. Un incendio cambia il suolo e quindi l'alluvione futura; una
pioggia estrema colpisce frana e alluvione insieme senza che l'una causi
l'altra. Regole diverse, forme diverse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from limen.core.cascades.config import JointRainRule, PostFireFloodRule
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel

__all__ = ["JointCell", "joint_rain_cells", "post_fire_flood_multiplier"]

_LEVEL_ORDER: tuple[RiskLevel, ...] = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)


def _at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(threshold)


def post_fire_flood_multiplier(
    months_since_fire: float | None, *, rule: PostFireFloodRule
) -> float:
    """Amplificazione del ramo pluviale su un suolo percorso dal fuoco.

    Restituisce un moltiplicatore in ``[1.0, rule.max_multiplier]``. Vale
    esattamente 1.0 — nessuna amplificazione — quando non c'è un incendio
    recente, quando la regola è spenta, o quando la finestra è chiusa.

    La curva è una campana centrata su ``peak_months``: l'effetto non è
    massimo subito perché serve che la pioggia trovi la crosta idrofobica
    ancora intatta, e decade con la ricrescita della vegetazione.

    ``None`` significa "nessun incendio noto", che non è "incendio molto
    vecchio": entrambi danno 1.0, ma sono fatti diversi e il chiamante che
    volesse distinguerli ha il dato a monte.
    """
    if not rule.enabled or months_since_fire is None:
        return 1.0
    if months_since_fire < 0.0 or months_since_fire > rule.window_months:
        return 1.0
    bell = math.exp(-((months_since_fire - rule.peak_months) ** 2) / rule.curve_denominator)
    return 1.0 + (rule.max_multiplier - 1.0) * bell


@dataclass(frozen=True, slots=True)
class JointCell:
    """Una cella che supera la soglia di due pericoli nella stessa finestra."""

    cell_id: str
    #: I pericoli coinvolti, con la classe raggiunta da ciascuno.
    levels: dict[HazardType, RiskLevel]
    #: Il punteggio più alto fra i pericoli coinvolti, per ordinare la lista.
    worst_score: float

    @property
    def hazards(self) -> tuple[HazardType, ...]:
        """I pericoli, in ordine stabile: due esecuzioni danno la stessa lista."""
        return tuple(sorted(self.levels, key=lambda h: h.value))


def joint_rain_cells(
    per_hazard: dict[HazardType, dict[str, tuple[RiskLevel, float, datetime]]],
    *,
    rule: JointRainRule,
    now: datetime,
) -> list[JointCell]:
    """Le celle che meritano **un** messaggio invece di due.

    ``per_hazard`` mappa ogni pericolo alle sue celle:
    ``{cell_id: (classe, punteggio, momento della valutazione)}``.

    Una cella entra quando almeno due pericoli la portano a
    ``rule.min_level`` o oltre, **e** le rispettive valutazioni cadono entro
    ``rule.window_hours`` da ``now``. La finestra serve perché gli sweep dei
    pericoli girano in momenti diversi: senza, la lettura di ieri di un
    pericolo si combinerebbe con quella di adesso dell'altro e produrrebbe un
    allarme congiunto che non è mai esistito in nessun istante.

    Ordinate per punteggio peggiore decrescente, con il cell_id a spareggio:
    la lista finisce in un messaggio, e un ordine instabile la farebbe
    sembrare cambiata a ogni ciclo.
    """
    if not rule.enabled:
        return []

    cutoff = now - timedelta(hours=rule.window_hours)
    by_cell: dict[str, dict[HazardType, tuple[RiskLevel, float]]] = {}
    for hazard, cells in per_hazard.items():
        for cell_id, (level, score, seen_at) in cells.items():
            if seen_at < cutoff or not _at_least(level, rule.min_level):
                continue
            by_cell.setdefault(cell_id, {})[hazard] = (level, score)

    joint = [
        JointCell(
            cell_id=cell_id,
            levels={h: lvl for h, (lvl, _) in found.items()},
            worst_score=max(score for _, score in found.values()),
        )
        for cell_id, found in by_cell.items()
        if len(found) >= 2
    ]
    joint.sort(key=lambda j: (-j.worst_score, j.cell_id))
    return joint
