"""Anthropic Claude factory.

Uses the official ``anthropic`` Python SDK. The import is guarded so
the package can be imported without the optional dependency installed
— the factory only fails at construction time when the user actually
selects this provider without the SDK.
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
class AnthropicChatClient:  # Implements the ChatClient Protocol structurally
    api_key: SecretStr
    model: str

    def __post_init__(self) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:  # pragma: no cover - covered by factory error
            raise LlmFactoryError(
                "Anthropic factory requires the 'agents' dependency group: "
                "`uv sync --group agents`."
            ) from e
        self._client = AsyncAnthropic(api_key=self.api_key.get_secret_value())

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str = "text",  # noqa: ARG002 — Anthropic uses tool-use for JSON
    ) -> str:
        from typing import Any

        # Anthropic's API takes system prompt separately from the message list.
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
        log.debug("anthropic.chat", model=self.model, n_messages=len(messages))
        response = await self._client.messages.create(**kwargs)
        # response.content is a list of blocks; concatenate text blocks only.
        parts: list[str] = []
        for block in response.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
        return "".join(parts)


@dataclass
class AnthropicFactory:  # Implements the LlmClientFactory Protocol structurally
    api_key: SecretStr
    role_models: dict[str, str]
    provider: str = "anthropic"
    default_model: str = "claude-haiku-4-5"

    def create(self, agent_role: str) -> ChatClient:
        model = self.role_models.get(agent_role, self.default_model)
        return AnthropicChatClient(api_key=self.api_key, model=model)
