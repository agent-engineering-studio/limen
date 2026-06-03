"""LLM-factory resolver precedence + override tests.

All deterministic; no network. Settings are built from the in-memory
model rather than env vars to keep tests hermetic.
"""

from __future__ import annotations

import pytest

from limen.agents.llm_factory.anthropic_factory import AnthropicFactory
from limen.agents.llm_factory.base import LlmFactoryError
from limen.agents.llm_factory.foundry_factory import FoundryFactory
from limen.agents.llm_factory.ollama_factory import OllamaFactory
from limen.agents.llm_factory.openai_factory import OpenAIFactory
from limen.agents.llm_factory.resolver import resolve_llm_factory
from limen.config.settings import LLMProvider, Settings


def _settings(**overrides: object) -> Settings:
    return Settings.model_validate(overrides)


def test_precedence_anthropic_wins_over_openai() -> None:
    s = _settings(anthropic_api_key="ak-xxx", openai_api_key="ok-yyy")
    f = resolve_llm_factory(s)
    assert isinstance(f, AnthropicFactory)
    assert f.provider == "anthropic"


def test_precedence_openai_when_no_anthropic() -> None:
    s = _settings(openai_api_key="ok-yyy")
    f = resolve_llm_factory(s)
    assert isinstance(f, OpenAIFactory)
    assert f.provider == "openai"


def test_precedence_foundry_when_no_anthropic_no_openai() -> None:
    s = _settings(
        azure_ai_endpoint="https://aoai.example",
        azure_ai_api_key="azkey",
    )
    f = resolve_llm_factory(s)
    assert isinstance(f, FoundryFactory)
    assert f.provider == "foundry"


def test_precedence_foundry_anthropic_variant() -> None:
    """ANTHROPIC_FOUNDRY_* alone also picks Foundry."""
    s = _settings(
        anthropic_foundry_endpoint="https://foundry.example",
        anthropic_foundry_api_key="afkey",
    )
    f = resolve_llm_factory(s)
    assert isinstance(f, FoundryFactory)


def test_fallback_ollama() -> None:
    s = _settings()
    f = resolve_llm_factory(s)
    assert isinstance(f, OllamaFactory)
    assert f.provider == "ollama"


def test_explicit_override_wins_over_keys() -> None:
    """LLM__PROVIDER=ollama beats an Anthropic key being present."""
    s = _settings(
        anthropic_api_key="ak-xxx",
        llm={"provider": "ollama"},
    )
    f = resolve_llm_factory(s)
    assert isinstance(f, OllamaFactory)


def test_explicit_override_to_anthropic_requires_key() -> None:
    s = _settings(llm={"provider": "anthropic"})
    with pytest.raises(LlmFactoryError, match=r"ANTHROPIC_API_KEY"):
        resolve_llm_factory(s)


def test_explicit_override_to_foundry_requires_endpoint_pair() -> None:
    s = _settings(llm={"provider": "foundry"})
    with pytest.raises(LlmFactoryError, match=r"Foundry"):
        resolve_llm_factory(s)


def test_role_models_match_settings_defaults() -> None:
    s = _settings(anthropic_api_key="ak-xxx")
    f = resolve_llm_factory(s)
    assert isinstance(f, AnthropicFactory)
    # Role -> model mapping must surface the LLMModels defaults
    assert f.role_models["RiskAnalyst"] == "claude-haiku-4-5"
    assert f.role_models["Briefing"] == "claude-sonnet-4-6"


def test_provider_label_matches_resolved_factory() -> None:
    """Anthropic/OpenAI keys give the expected `.provider` string."""
    assert resolve_llm_factory(_settings(anthropic_api_key="a")).provider == "anthropic"
    assert resolve_llm_factory(_settings(openai_api_key="o")).provider == "openai"
    assert resolve_llm_factory(_settings()).provider == "ollama"


def test_explicit_override_value_in_llm_provider_uses_enum() -> None:
    s = _settings(llm={"provider": LLMProvider.OLLAMA.value})
    assert isinstance(resolve_llm_factory(s), OllamaFactory)
