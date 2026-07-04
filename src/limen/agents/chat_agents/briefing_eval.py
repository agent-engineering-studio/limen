"""Deterministic fidelity checks for LLM briefings (B3 eval).

The briefing prompt states binding rules ("Verrà controllata in
post-processing") that nothing actually checked until now: length 150-250
words, no invented numbers, no bullet lists, no alarm terms, no imperatives.
This module is that check — pure functions, no LLM, no I/O — usable both as
an offline eval over stored briefings and, later, as a runtime guard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Structural tokens that legitimately appear without being "assessment
# numbers": monitoring horizons and the API/soil window names.
_STRUCTURAL_NUMBERS = {"7", "24", "28", "30", "48", "60", "72", "90"}

_BANNED_TERMS = ("emergenza", "catastrofe")
_BANNED_IMPERATIVES = ("dovreste", "evacuare", "evacuate")

_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|#{1,6}\s)", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class BriefingEval:
    word_count: int
    violations: list[str] = field(default_factory=list)
    unknown_numbers: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def allowed_numbers_from_payload(payload: Any) -> set[str]:
    """Collect every numeric token of an assessment payload, in the textual
    variants a briefing may quote (int, 1dp, 2dp, comma or dot decimals)."""
    out: set[str] = set(_STRUCTURAL_NUMBERS)

    def _add(v: float) -> None:
        for s in (
            f"{v:.2f}",
            f"{v:.1f}",
            f"{v:.0f}",
            str(int(v)) if float(v).is_integer() else None,
        ):
            if s is not None:
                out.add(s)
                out.add(s.replace(".", ","))

    def _walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            _add(float(node))
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(payload)
    return out


def evaluate_briefing(
    text: str,
    *,
    allowed_numbers: set[str],
    min_words: int = 150,
    max_words: int = 250,
) -> BriefingEval:
    """Check one briefing against the prompt's binding rules."""
    violations: list[str] = []
    words = len(text.split())
    if not min_words <= words <= max_words:
        violations.append(f"lunghezza {words} parole (richieste {min_words}-{max_words})")

    if _BULLET_RE.search(text):
        violations.append("contiene elenchi puntati o titoli markdown (vietati)")

    lower = text.lower()
    for term in _BANNED_TERMS:
        if term in lower:
            violations.append(f"termine di allarme vietato: {term!r}")
    for term in _BANNED_IMPERATIVES:
        if term in lower:
            violations.append(f"imperativo agli operatori vietato: {term!r}")

    unknown = sorted(
        {
            n
            for n in _NUMBER_RE.findall(text)
            if n not in allowed_numbers and n.replace(",", ".") not in allowed_numbers
        }
    )
    if unknown:
        violations.append(f"numeri non presenti nell'assessment: {unknown}")

    return BriefingEval(word_count=words, violations=violations, unknown_numbers=unknown)
