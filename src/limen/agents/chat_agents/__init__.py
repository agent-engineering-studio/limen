"""LLM-backed ChatAgents for the Limen workflow.

Two agents:

* :class:`RiskAnalystAgent` — produces a strictly-typed
  :class:`RiskAnalysis` JSON object that summarises the engine's
  numeric breakdown.
* :class:`BriefingAgent` — produces a 150-250 word Italian briefing
  paragraph.

Both agents are **non-authoritative**: they only reformulate the
deterministic engine's output. Tests assert that they never alter
``score`` or ``breakdown``.
"""

from limen.agents.chat_agents.briefing import BriefingAgent
from limen.agents.chat_agents.risk_analyst import (
    RiskAnalysis,
    RiskAnalystAgent,
)

__all__ = ["BriefingAgent", "RiskAnalysis", "RiskAnalystAgent"]
