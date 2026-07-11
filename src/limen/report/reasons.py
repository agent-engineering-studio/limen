"""Motivo del rischio in linguaggio piano — deterministico, dal breakdown.

Port di plainSummary/verdict in frontend/src/components/CellPopup.tsx.
Niente LLM, niente numeri inventati: solo i contributi componenti S/M/E/F/H.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from limen.core.models.risk import RiskLevel

_DRIVERS: list[tuple[str, str]] = [
    ("s", "dalla natura del versante: geologia, pendenza e frane del passato"),
    ("m", "dalla spinta della pioggia recente"),
    ("e", "dalle scosse sismiche recenti"),
    ("f", "dall'effetto di incendi recenti"),
    ("h", "dalla pericolosità idraulica della zona"),
]


@dataclass(frozen=True)
class Verdict:
    text: str
    tone: Literal["ok", "watch", "warn"]


def verdict(level: RiskLevel) -> Verdict:
    if level in (RiskLevel.VeryHigh, RiskLevel.High):
        return Verdict("Da attenzionare: rischio alto sul versante.", "warn")
    if level is RiskLevel.Moderate:
        return Verdict("Da tenere sotto osservazione: rischio moderato.", "watch")
    return Verdict("Nessuna preoccupazione immediata: rischio basso.", "ok")


def plain_summary(*, s: float, m: float, e: float, f: float, h: float) -> str:
    scalars = {"s": s, "m": m, "e": e, "f": f, "h": h}
    parts: list[str] = []
    top_key, top_phrase = max(_DRIVERS, key=lambda d: scalars[d[0]])
    if scalars[top_key] > 0.05:
        parts.append(f"Il punteggio nasce soprattutto {top_phrase}.")
    if m < 0.05:
        parts.append(
            "Non c'è pioggia in corso: il punteggio riflette la fragilità "
            "storica del versante, non un pericolo in atto."
        )
    elif m < 0.2:
        parts.append("La pioggia recente incide poco.")
    elif m < 0.5:
        parts.append("La pioggia recente contribuisce in modo moderato.")
    else:
        parts.append("La pioggia recente sta spingendo il rischio verso l'alto.")
    return " ".join(parts)
