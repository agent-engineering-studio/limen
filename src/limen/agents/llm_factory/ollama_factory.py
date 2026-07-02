"""Ollama (OpenAI-compatible) factory.

Ollama exposes an ``/v1/chat/completions`` endpoint that mimics the
OpenAI shape. We call it directly with the shared httpx client; no
SDK dependency. Suited for the Aruba VPS deployment where Ollama runs
as a sibling container.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)


@dataclass
class OllamaChatClient:  # Implements the ChatClient Protocol structurally
    base_url: str
    model: str
    # Bearer token for Ollama Cloud (https://ollama.com). None ⇒ host Ollama,
    # which needs no auth. The endpoint shape is identical either way.
    api_key: str | None = None

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        response_format: str = "text",
    ) -> str:
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        client = await SharedHttpClient.get()
        log.debug("ollama.chat", model=self.model, url=url, n_messages=len(messages))
        resp = await fetch_with_retry("POST", url, client=client, json=payload, headers=headers)
        data = resp.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected Ollama response shape: {exc}") from exc


@dataclass
class OllamaFactory:  # Implements the LlmClientFactory Protocol structurally
    """Per-role :class:`ChatClient` builder for Ollama."""

    base_url: str
    role_models: dict[str, str]
    provider: str = "ollama"
    default_model: str = "qwen2.5:32b"
    api_key: str | None = None

    def create(self, agent_role: str) -> ChatClient:
        model = self.role_models.get(agent_role, self.default_model)
        return OllamaChatClient(base_url=self.base_url, model=model, api_key=self.api_key)
