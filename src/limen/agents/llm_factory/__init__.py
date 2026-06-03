"""LLM factory + resolver.

Public surface:

* :class:`ChatMessage` / :class:`ChatClient` — vendor-agnostic Protocols.
* :class:`LlmClientFactory` — produces a :class:`ChatClient` for a given
  agent role (``"RiskAnalyst"`` / ``"Briefing"`` in V1).
* :func:`resolve_llm_factory` — picks the concrete factory using the
  precedence ``override > Anthropic > OpenAI > Foundry > Ollama``.
* :class:`StubChatClient` / :class:`StubLlmClientFactory` — deterministic
  test doubles (used by ``tests/e2e``).
"""

from limen.agents.llm_factory.base import (
    ChatClient,
    ChatMessage,
    LlmClientFactory,
    LlmFactoryError,
)
from limen.agents.llm_factory.resolver import resolve_llm_factory
from limen.agents.llm_factory.stub import StubChatClient, StubLlmClientFactory

__all__ = [
    "ChatClient",
    "ChatMessage",
    "LlmClientFactory",
    "LlmFactoryError",
    "StubChatClient",
    "StubLlmClientFactory",
    "resolve_llm_factory",
]
