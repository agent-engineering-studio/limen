"""Construction smoke tests for every concrete :class:`LlmClientFactory`.

The factories lazily import their SDKs and instantiate a client inside
``__post_init__``. These tests prove that the construction code path
runs with valid creds — they do NOT make any network call.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from limen.agents.llm_factory.anthropic_factory import (
    AnthropicChatClient,
    AnthropicFactory,
)
from limen.agents.llm_factory.foundry_factory import (
    FoundryAnthropicChatClient,
    FoundryAzureOpenAIChatClient,
    FoundryFactory,
)
from limen.agents.llm_factory.ollama_factory import (
    OllamaChatClient,
    OllamaFactory,
)
from limen.agents.llm_factory.openai_factory import (
    OpenAIChatClient,
    OpenAIFactory,
)

ROLE_MODELS = {
    "RiskAnalyst": "model-a",
    "Briefing": "model-b",
}


def test_anthropic_factory_create_returns_client() -> None:
    factory = AnthropicFactory(api_key=SecretStr("ak-test"), role_models=ROLE_MODELS)
    client = factory.create("RiskAnalyst")
    assert isinstance(client, AnthropicChatClient)
    assert client.model == "model-a"
    # Fallback to default model when role is unknown.
    fallback = factory.create("UnknownRole")
    assert isinstance(fallback, AnthropicChatClient)
    assert fallback.model == factory.default_model


def test_openai_factory_create_returns_client() -> None:
    factory = OpenAIFactory(api_key=SecretStr("sk-test"), role_models=ROLE_MODELS)
    client = factory.create("Briefing")
    assert isinstance(client, OpenAIChatClient)
    assert client.model == "model-b"


def test_openai_factory_supports_custom_base_url() -> None:
    factory = OpenAIFactory(
        api_key=SecretStr("sk-test"),
        role_models=ROLE_MODELS,
        base_url="https://openai-compatible.example/v1",
    )
    client = factory.create("RiskAnalyst")
    assert isinstance(client, OpenAIChatClient)
    assert client.base_url == "https://openai-compatible.example/v1"


def test_ollama_factory_create_returns_client() -> None:
    factory = OllamaFactory(
        base_url="http://ollama.test:11434",
        role_models=ROLE_MODELS,
    )
    client = factory.create("RiskAnalyst")
    assert isinstance(client, OllamaChatClient)
    assert client.model == "model-a"
    assert client.base_url == "http://ollama.test:11434"


def test_foundry_factory_prefers_anthropic_endpoint() -> None:
    factory = FoundryFactory(
        role_models=ROLE_MODELS,
        anthropic_endpoint="https://foundry.example",
        anthropic_api_key=SecretStr("afk"),
        azure_endpoint="https://aoai.example",
        azure_api_key=SecretStr("azk"),
    )
    client = factory.create("RiskAnalyst")
    # Anthropic flavour wins when both pairs are configured (mirrors the
    # global Anthropic > OpenAI precedence).
    assert isinstance(client, FoundryAnthropicChatClient)


def test_foundry_factory_falls_back_to_azure() -> None:
    factory = FoundryFactory(
        role_models=ROLE_MODELS,
        azure_endpoint="https://aoai.example",
        azure_api_key=SecretStr("azk"),
    )
    client = factory.create("RiskAnalyst")
    assert isinstance(client, FoundryAzureOpenAIChatClient)


def test_foundry_factory_without_any_pair_raises() -> None:
    factory = FoundryFactory(role_models=ROLE_MODELS)
    from limen.agents.llm_factory.base import LlmFactoryError

    with pytest.raises(LlmFactoryError, match=r"endpoint\+key"):
        factory.create("RiskAnalyst")
