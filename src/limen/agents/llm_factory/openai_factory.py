"""OpenAI chat-completions factory.

Uses the official ``openai`` Python SDK (async). Guarded import — the
factory only constructs the SDK client when the provider is actually
selected.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from limen.agents.llm_factory.base import (
    ChatClient,
    ChatMessage,
    LlmClientFactory,
    LlmFactoryError,
)
from limen.core.logging import get_logger

if TYPE_CHECKING:
    from pydantic import SecretStr

log = get_logger(__name__)


@dataclass
class OpenAIChatClient(ChatClient):
    api_key: SecretStr
    model: str
    base_url: str | None = None

    def __post_init__(self) -> None:
        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover
            raise LlmFactoryError(
                "OpenAI factory requires the 'agents' dependency group: `uv sync --group agents`."
            ) from e
        kwargs: dict[str, object] = {"api_key": self.api_key.get_secret_value()}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str = "text",
    ) -> str:
        log.debug("openai.chat", model=self.model, n_messages=len(messages))
        kwargs: dict[str, object] = {
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
class OpenAIFactory(LlmClientFactory):
    api_key: SecretStr
    role_models: dict[str, str]
    provider: str = "openai"
    default_model: str = "gpt-4o-mini"
    base_url: str | None = None

    def create(self, agent_role: str) -> ChatClient:
        model = self.role_models.get(agent_role, self.default_model)
        return OpenAIChatClient(api_key=self.api_key, model=model, base_url=self.base_url)
