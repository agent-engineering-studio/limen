"""Render a :class:`GroundingResult` into a Markdown citation block.

Deterministic. No LLM. The block is appended verbatim to the briefing
narrative, so the briefing's source attribution is fully auditable —
nothing here is invented.
"""

from __future__ import annotations

from limen.knowledge.schema import GroundingResult

_HEADER_IT = "**Fonti**"


def format_citations(result: GroundingResult, *, max_items: int = 3) -> str:
    """Markdown citation block in Italian. Empty result → empty string.

    The output is intentionally short — the BriefingAgent enforces a
    150-250 word ceiling, and citations sit *outside* that count by
    being appended after the narrative.
    """
    if not result.passages:
        return ""
    lines = [_HEADER_IT]
    for p in result.passages[:max_items]:
        title = p.title or p.source
        citation = p.citation or p.source
        if citation and citation != title:
            lines.append(f"- {title} — {citation}")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)


__all__ = ["format_citations"]
