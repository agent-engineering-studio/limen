"""Microsoft Foundry factory.

Two Foundry surfaces are supported:

* **Azure OpenAI on Foundry** — same wire format as OpenAI, accessed via
  the ``AZURE_AI_ENDPOINT`` + ``AZURE_AI_API_KEY`` env vars.
* **Anthropic on Foundry** — Claude served from Foundry, accessed via
  ``ANTHROPIC_FOUNDRY_ENDPOINT`` + ``ANTHROPIC_FOUNDRY_API_KEY``.

Both ultimately speak the same chat-completions shape, so we reuse the
OpenAI SDK with a custom ``base_url`` for the Azure OpenAI flavour, and
the Anthropic SDK with a custom ``base_url`` for the Claude flavour.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from limen.agents.llm_factory.base import (
    ChatClient,
    ChatMessage,
    LlmFactoryError,
)
from limen.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic import SecretStr

log = get_logger(__name__)


@dataclass
class FoundryAzureOpenAIChatClient:  # Implements the ChatClient Protocol structurally
    endpoint: str
    api_key: SecretStr
    model: str

    def __post_init__(self) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as e:  # pragma: no cover
            raise LlmFactoryError(
                "Foundry (Azure OpenAI) factory requires the 'agents' dependency group: "
                "`uv sync --group agents`."
            ) from e
        self._client = AsyncOpenAI(
            api_key=self.api_key.get_secret_value(),
            base_url=self.endpoint.rstrip("/"),
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str = "text",
    ) -> str:
        from typing import Any

        log.debug("foundry.aoai.chat", model=self.model, n_messages=len(messages))
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content
        return content or ""


@dataclass
class FoundryAnthropicChatClient:  # Implements the ChatClient Protocol structurally
    endpoint: str
    api_key: SecretStr
    model: str

    def __post_init__(self) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:  # pragma: no cover
            raise LlmFactoryError(
                "Foundry (Anthropic) factory requires the 'agents' dependency group: "
                "`uv sync --group agents`."
            ) from e
        self._client = AsyncAnthropic(
            api_key=self.api_key.get_secret_value(),
            base_url=self.endpoint.rstrip("/"),
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str = "text",  # noqa: ARG002
    ) -> str:
        from typing import Any

        system_parts = [m.content for m in messages if m.role == "system"]
        body = [
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
            for m in messages
            if m.role != "system"
        ]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": body,
            "temperature": temperature,
            "max_tokens": max_tokens or 1024,
        }
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)
        log.debug("foundry.anthropic.chat", model=self.model, n_messages=len(messages))
        response = await self._client.messages.create(**kwargs)
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        return "".join(parts)


@dataclass
class FoundryFactory:  # Implements the LlmClientFactory Protocol structurally
    """Builds the right Foundry client based on which credentials are set.

    If both Anthropic-on-Foundry and Azure-OpenAI-on-Foundry credentials
    are provided, **Anthropic wins** (consistent with the global precedence).
    """

    role_models: dict[str, str]
    provider: str = "foundry"
    azure_endpoint: str | None = None
    azure_api_key: SecretStr | None = None
    anthropic_endpoint: str | None = None
    anthropic_api_key: SecretStr | None = None
    default_model: str = "gpt-4o-mini"

    def create(self, agent_role: str) -> ChatClient:
        model = self.role_models.get(agent_role, self.default_model)
        if self.anthropic_endpoint and self.anthropic_api_key:
            return FoundryAnthropicChatClient(
                endpoint=self.anthropic_endpoint,
                api_key=self.anthropic_api_key,
                model=model,
            )
        if self.azure_endpoint and self.azure_api_key:
            return FoundryAzureOpenAIChatClient(
                endpoint=self.azure_endpoint,
                api_key=self.azure_api_key,
                model=model,
            )
        raise LlmFactoryError(
            "FoundryFactory was constructed without any concrete endpoint+key pair"
        )
