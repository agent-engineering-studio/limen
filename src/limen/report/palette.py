"""Palette rischio server-side — mirror di frontend/src/lib/risk-colors.ts.

Duplicata di proposito: il report gira server-side e non può importare il TS.
ColorBrewer YlOrRd, 5 classi, mai solo-colore (label + range accanto al colore).
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
    RiskClass(RiskLevel.None_, "Nessuno", "#ffffb2", (0.0, 0.15)),
    RiskClass(RiskLevel.Low, "Basso", "#fecc5c", (0.15, 0.35)),
    RiskClass(RiskLevel.Moderate, "Moderato", "#fd8d3c", (0.35, 0.55)),
    RiskClass(RiskLevel.High, "Alto", "#f03b20", (0.55, 0.75)),
    RiskClass(RiskLevel.VeryHigh, "Molto alto", "#bd0026", (0.75, 1.0)),
]

_BY_LEVEL = {c.level: c for c in RISK_CLASSES}


def color_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].color


def label_for(level: RiskLevel) -> str:
    return _BY_LEVEL[level].label_it
