"""Palette rischio server-side — mirror di frontend/src/lib/risk-colors.ts.

Duplicata di proposito: il report gira server-side e non può importare il TS.
Stessa scala della sala operativa (#155), mai solo-colore (label + range
accanto al colore). Cambia lì, cambia qui: un colore deve voler dire la stessa
classe nella SPA e nel report.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.core.models.risk import RiskLevel


@dataclass(frozen=True)
class RiskClass:
    level: RiskLevel
    label_it: str
    color: str
    range: tuple[float, float]


RISK_CLASSES: list[RiskClass] = [
    RiskClass(RiskLevel.None_, "Nessuno", "#151c25", (0.0, 0.15)),
    RiskClass(RiskLevel.Low, "Basso", "#134d47", (0.15, 0.35)),
    RiskClass(RiskLevel.Moderate, "Moderato", "#f2d45c", (0.35, 0.55)),
    RiskClass(RiskLevel.High, "Alto", "#f58a30", (0.55, 0.75)),
    RiskClass(RiskLevel.VeryHigh, "Molto alto", "#e33f5a", (0.75, 1.0)),
]

_BY_LEVEL = {c.level: c for c in RISK_CLASSES}


def color_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].color


# Nessuno e basso sono tinte scure; dal moderato in su chiare, e il bianco sul
# giallo starebbe a 1,4:1.
_SCURE = frozenset({RiskLevel.None_, RiskLevel.Low})


def text_color_for(level: RiskLevel) -> str:
    """Il colore del testo sopra il colore di classe."""
    return "#ffffff" if level in _SCURE else "#1a0f05"


def label_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].label_it
