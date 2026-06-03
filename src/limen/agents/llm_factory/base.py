"""Vendor-agnostic chat-client Protocols.

The intent is *minimal*: every executor + agent code path only depends
on :class:`ChatClient`. Provider SDKs (Anthropic, OpenAI, …) live behind
concrete factories that lazily import their dependencies.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One chat turn — the same DTO whatever the backing provider."""

    role: Role
    content: str


class LlmFactoryError(RuntimeError):
    """Raised when a factory can't be constructed (missing SDK, missing creds)."""


@runtime_checkable
class ChatClient(Protocol):
    """A thin async chat-completion abstraction.

    Implementations must:

    * Be **deterministic given the same inputs and a temperature of 0**
      (best-effort — vendors may drift; we don't depend on it).
    * Return raw text. JSON / Pydantic schemas live one layer up in the
      ChatAgent's response-validation logic.
    """

    @property
    def model(self) -> str:
        """The concrete model id this client targets."""
        ...

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: Literal["text", "json_object"] = "text",
    ) -> str:
        """Return the assistant message content for ``messages``."""


@runtime_checkable
class LlmClientFactory(Protocol):
    """Builds a :class:`ChatClient` for a given agent role."""

    @property
    def provider(self) -> str:
        """A short label for the provider (``"anthropic"``, ``"openai"``…)."""
        ...

    def create(self, agent_role: str) -> ChatClient:
        """Construct the client for ``agent_role`` (``"RiskAnalyst"`` etc.)."""
        ...
