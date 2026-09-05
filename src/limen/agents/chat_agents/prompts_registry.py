"""Which hazards have an operator-facing narrative, and where its prompt lives.

The Italian prompts are written for a specific danger — the briefing one opens
with *"spiega il rischio frane"* and the RiskAnalyst schema's ``driver`` enum
lists only slope-failure causes. Running them on a wildfire assessment gives a
landslide persona narrating a fire: sometimes it lands right by luck, sometimes
it explains a rainfall threshold that was never computed.

That is worse than no narrative. The scoring, the alerts and the map are all
deterministic and unaffected — the LLM only ever reformulates — so a hazard
without a prompt simply ships without prose, and says so in the log.

Adding one is a **file drop**: name it ``<agent>.<hazard>.it.md`` next to the
landslide files and it is picked up here, no code change. The RiskAnalyst
schema's ``driver`` values would need extending too, which is why the wildfire
prompts are a deliberate follow-up rather than something improvised here.
"""

from __future__ import annotations

from importlib import resources

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType

PROMPT_PACKAGE = "limen.agents.chat_agents.prompts"


def prompt_file(agent: str, hazard: HazardType) -> str | None:
    """Return the prompt filename for ``(agent, hazard)``, or ``None``.

    The default hazard keeps the unsuffixed filename the repo already ships,
    so nothing about the landslide path moves.
    """
    candidate = (
        f"{agent}.it.md" if hazard is DEFAULT_HAZARD else f"{agent}.{hazard.value}.it.md"
    )
    if resources.files(PROMPT_PACKAGE).joinpath(candidate).is_file():
        return candidate
    return None


def has_narrative(hazard: HazardType) -> bool:
    """True when *both* narrative agents have a prompt for ``hazard``.

    Both, not either: the briefing prompt reads the RiskAnalyst's structured
    output, so half a pair would produce a narrative missing its own analysis.
    """
    return all(prompt_file(agent, hazard) is not None for agent in ("briefing", "risk_analyst"))


__all__ = ["PROMPT_PACKAGE", "has_narrative", "prompt_file"]
