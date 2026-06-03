"""LLM provider resolver.

This is a *stub*: it only encodes the precedence rules (Anthropic > OpenAI >
Foundry > Ollama) so that downstream code can already query
:func:`resolve_provider` without circular dependencies. The actual provider
clients land in a later prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.config.settings import LLMProvider, Settings, get_settings


@dataclass(frozen=True, slots=True)
class ResolvedProvider:
    provider: LLMProvider
    reason: str


def resolve_provider(settings: Settings | None = None) -> ResolvedProvider:
    """Resolve which LLM provider should be used.

    Order:
        1. Explicit ``LLM__PROVIDER`` override.
        2. ``ANTHROPIC_API_KEY`` present → Anthropic.
        3. ``OPENAI_API_KEY`` present → OpenAI.
        4. Foundry endpoint + key present → Foundry.
        5. Default → Ollama (local).
    """
    s = settings or get_settings()

    if s.llm.provider is not None:
        return ResolvedProvider(s.llm.provider, "explicit LLM__PROVIDER override")

    if s.anthropic_api_key is not None:
        return ResolvedProvider(LLMProvider.ANTHROPIC, "ANTHROPIC_API_KEY present")

    if s.openai_api_key is not None:
        return ResolvedProvider(LLMProvider.OPENAI, "OPENAI_API_KEY present")

    if s.foundry_endpoint and s.foundry_api_key is not None:
        return ResolvedProvider(LLMProvider.FOUNDRY, "Foundry endpoint+key present")

    return ResolvedProvider(
        LLMProvider.OLLAMA, "no cloud provider credentials; using Ollama fallback"
    )
