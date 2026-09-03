"""llama.cpp (OpenAI-compatible) factory.

``llama-server`` — and ``llama-swap`` in front of it — expose
``/v1/chat/completions`` with the OpenAI request/response shape, so we call it
directly with the shared httpx client and no SDK dependency, exactly as the
Ollama factory does.

This is the engine of the self-hosted inference server: a single GPU serving
one chat model at a time, with llama-swap loading the requested model on
demand. Claude stays available as an opt-in alternative via ``ANTHROPIC_API_KEY``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

# A request that arrives while llama-swap is loading a different model blocks
# until the swap completes, so this ceiling covers swap + prompt processing +
# generation. On the reference host the GGUFs now sit on striped NVMe and a
# load is seconds, not the ~2 minutes the previous 600 s default was budgeting
# for on spinning disks — the models behind the gateway that serve agent roles
# (fast/chat/extract) are GPU-resident and answer in seconds.
#
# Too high a ceiling is as harmful as too low, in the opposite direction. Too
# low cuts off a healthy model mid-answer. Too high makes a *broken* engine
# indistinguishable from a slow one for as long as the ceiling lasts: the
# caller blocks, times out, falls back to the deterministic path anyway, and
# the only difference the extra wait bought is that you found out later. A role
# deliberately pointed at a slow model gets its own ceiling via
# ``role_timeouts`` rather than raising this one for everybody.
DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass
class LlamaCppChatClient:  # Implements the ChatClient Protocol structurally
    base_url: str
    model: str
    # llama-server accepts --api-key; when it is not configured the endpoint
    # needs no auth. Same request shape either way.
    api_key: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

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
            # llama.cpp implements this by constraining sampling with a JSON
            # grammar, so the output is well-formed by construction rather than
            # by the model's good behaviour.
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        client = await SharedHttpClient.get()
        log.debug("llamacpp.chat", model=self.model, url=url, n_messages=len(messages))
        resp = await fetch_with_retry(
            "POST",
            url,
            client=client,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        # `fetch_with_retry` RETURNS non-retryable 4xx rather than raising, so
        # without this check a wrong base_url (a 404 from some other service on
        # the port) surfaced as "unexpected response shape: 'choices'" —
        # pointing at the parser instead of at the misconfiguration.
        if resp.status_code >= 400:
            raise RuntimeError(
                f"llama.cpp endpoint returned HTTP {resp.status_code} for {url} "
                f"(model={self.model!r}): {resp.text[:200]}"
            )
        data = resp.json()
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"unexpected llama.cpp response shape: {exc}") from exc


@dataclass
class LlamaCppFactory:  # Implements the LlmClientFactory Protocol structurally
    """Per-role :class:`ChatClient` builder for llama.cpp / llama-swap."""

    base_url: str
    role_models: dict[str, str]
    provider: str = "llamacpp"
    default_model: str = "qwen3.5-9b"
    api_key: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    # Per-role ceiling, keyed by the same labels as ``role_models``. Roles
    # absent here use ``timeout_seconds``.
    role_timeouts: dict[str, float] = field(default_factory=dict)

    def create(self, agent_role: str) -> ChatClient:
        model = self.role_models.get(agent_role, self.default_model)
        return LlamaCppChatClient(
            base_url=self.base_url,
            model=model,
            api_key=self.api_key,
            timeout_seconds=self.role_timeouts.get(agent_role, self.timeout_seconds),
        )
