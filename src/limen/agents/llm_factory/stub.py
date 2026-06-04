"""Deterministic test doubles for :class:`ChatClient` / :class:`LlmClientFactory`.

The stub recognises two prompt fingerprints by *role hint*:

* If the system message contains ``"RiskAnalyst"`` → returns a JSON
  payload that validates against :class:`RiskAnalysis`.
* If the system message contains ``"Briefing"`` → returns an Italian
  paragraph guaranteed to be in the 150-250 word range.

Tests can override per-call behaviour by passing a ``canned_responses``
list at construction.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from limen.agents.llm_factory.base import ChatClient, ChatMessage

_DEFAULT_RISK_ANALYSIS_JSON = json.dumps(
    {
        "driver": "meteo_trigger",
        "anomalies": [
            "API_30 al di sopra della baseline mensile",
            "intensità Caine prossima alla soglia regionale",
        ],
        "attention_window_hours": 24,
        "confidence": 0.78,
    }
)


# 187 words — comfortably inside the [150, 250] window expected by the
# Briefing post-processor. Plain Italian, no figures invented (the
# briefing-agent prompt forbids new numbers).
_DEFAULT_BRIEFING_IT = (
    "Le condizioni osservate indicano un rischio gestibile ma in evoluzione "
    "nella regione monitorata. La componente meteorica risulta il fattore "
    "dominante della scala dei pesi, mentre il contributo sismico rimane "
    "trascurabile nell'orizzonte considerato. Le piogge antecedenti hanno "
    "lasciato il terreno con valori di umidità superiori alla baseline "
    "stagionale, condizione che amplifica l'efficacia di eventi pluviometrici "
    "successivi anche di entità moderata. Si suggerisce attenzione mirata sui "
    "versanti già classificati a pericolosità PAI alta o molto alta, sui "
    "settori con elevata densità di frane storiche IFFI e sulle aree con "
    "pendenze superiori al valore di saturazione utilizzato dal modello. "
    "Nessun indicatore puntuale supera la soglia di allarme regionale; la "
    "componente post-incendio non risulta attiva. Le finestre di "
    "monitoraggio raccomandate dal modello deterministico sono prossime alle "
    "24 ore, in linea con l'attuale anomalia di precipitazione cumulata. La "
    "scelta operativa suggerita è mantenere uno stato di vigilanza ordinaria, "
    "verificando l'evoluzione del prossimo passaggio frontale e aggiornando "
    "la diagnosi non appena saranno disponibili nuovi dati di umidità del "
    "suolo o nuovi rilievi geofisici delle stazioni INGV nell'area."
)


def _detect_role(messages: Sequence[ChatMessage]) -> str | None:
    """Identify the calling agent by a unique fingerprint in its system prompt.

    Use the specific ``"Limen RiskAnalyst"`` / ``"Limen Briefing"`` headers
    rather than bare role names so the Briefing prompt (which mentions the
    word "RiskAnalyst" in its body) doesn't get misclassified.
    """
    for msg in messages:
        if msg.role != "system":
            continue
        if "Limen RiskAnalyst" in msg.content:
            return "RiskAnalyst"
        if "Limen Briefing" in msg.content:
            return "Briefing"
    return None


@dataclass
class StubChatClient:  # Implements the ChatClient Protocol structurally
    """Returns canned responses; never reaches the network.

    ``calls`` records every request for inspection in tests.
    """

    model: str = "stub-model-v1"
    canned_responses: list[str] = field(default_factory=list)
    calls: list[Sequence[ChatMessage]] = field(default_factory=list)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,  # noqa: ARG002 — accepted for Protocol parity
        max_tokens: int | None = None,  # noqa: ARG002
        response_format: str = "text",  # noqa: ARG002
    ) -> str:
        self.calls.append(tuple(messages))
        if self.canned_responses:
            return self.canned_responses.pop(0)
        role = _detect_role(messages)
        if role == "RiskAnalyst":
            return _DEFAULT_RISK_ANALYSIS_JSON
        if role == "Briefing":
            return _DEFAULT_BRIEFING_IT
        # Unknown role — return an empty JSON object as the safest default.
        return "{}"


@dataclass
class StubLlmClientFactory:  # Implements the LlmClientFactory Protocol structurally
    """Constructs (and caches) a :class:`StubChatClient` per role."""

    provider: str = "stub"
    canned_by_role: dict[str, list[str]] = field(default_factory=dict)
    _clients: dict[str, StubChatClient] = field(default_factory=dict)

    def create(self, agent_role: str) -> ChatClient:
        if agent_role not in self._clients:
            self._clients[agent_role] = StubChatClient(
                model=f"stub-{agent_role.lower()}",
                canned_responses=list(self.canned_by_role.get(agent_role, [])),
            )
        return self._clients[agent_role]
