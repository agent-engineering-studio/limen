"""``limen llm-check`` — does the inference engine actually answer, per role?

Prints, for every agent role, the model it resolves to, its per-role timeout,
and the latency of a real round trip. Exits non-zero if any role
fails, so it works as a deploy gate as well as a diagnostic.

Runs entirely on ``Settings`` + the resolved factory: no database, no
ObjectStore. That is deliberate — the point is to be runnable from inside the
container (``docker compose exec api limen llm-check``), where ``127.0.0.1``
is the container itself and the gateway is only reachable through
``host.docker.internal``, so a check performed from the host proves nothing
about what the API process can see.
"""

from __future__ import annotations

import time

import httpx

from limen.agents.llm_factory.base import ChatMessage
from limen.agents.llm_factory.resolver import AGENT_ROLES, resolve_llm_factory, role_models
from limen.config.settings import SLOW_GENERATION_MODELS, LLMProvider, Settings, get_settings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)

# What this proves: the route resolves, the endpoint accepts the model name,
# and the response parses. It does NOT judge output quality — and with a
# reasoning model the whole budget can go to think-tokens, so an empty reply
# next to an `ok` is normal and still means the role is wired correctly.
_PROBE = [ChatMessage(role="user", content="Rispondi solo: ok")]
_PROBE_MAX_TOKENS = 16

# A health probe must fail fast. `fetch_with_retry` would spend four attempts
# with exponential backoff before admitting the gateway is down, which is the
# opposite of what a diagnostic wants — so this one call deliberately skips
# the shared retry policy while still using the shared client.
_CATALOGUE_TIMEOUT_SECONDS = 5.0


def _base_url(settings: Settings) -> str | None:
    """The engine's base URL, when the provider has a local one to probe."""
    provider = settings.llm.provider
    if provider is LLMProvider.LLAMACPP:
        return settings.llm.llamacpp_base_url
    if provider is LLMProvider.OLLAMA:
        return settings.llm.ollama_base_url
    return None


async def _catalogue(base_url: str, api_key: str | None) -> list[str] | None:
    """Model ids the gateway advertises, or None when it cannot be reached."""
    url = f"{base_url.rstrip('/')}/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    client = await SharedHttpClient.get()
    try:
        resp = await client.get(url, headers=headers, timeout=_CATALOGUE_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return [str(row["id"]) for row in resp.json()["data"]]
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        log.warning("llm_check.catalogue_unreachable", url=url, error=str(exc))
        return None


async def run() -> int:
    settings = get_settings()
    factory = resolve_llm_factory(settings)
    configured = role_models(settings)
    declared = settings.llm.models.model_fields_set

    print(f"provider: {factory.provider}")

    base_url = _base_url(settings)
    catalogue: list[str] | None = None
    if base_url is not None:
        print(f"base_url: {base_url}")
        key = settings.llm.llamacpp_api_key or settings.llm.ollama_api_key
        catalogue = await _catalogue(base_url, key.get_secret_value() if key else None)
        if catalogue is None:
            print("models:   UNREACHABLE — every role below will degrade")
        else:
            print(f"models:   {', '.join(sorted(catalogue))}")
    print()

    failures = 0
    for role in AGENT_ROLES:
        client = factory.create(role)
        # The factory owns the fallback rules, so read the model off the built
        # client rather than re-deriving it here and risking a different answer
        # than the one the workflow will actually get.
        model = str(getattr(client, "model", configured[role]))
        timeout = float(getattr(client, "timeout_seconds", 0.0))
        source = "declared" if role in declared else "fallback"

        notes = []
        if catalogue is not None and model not in catalogue:
            notes.append("NOT IN GATEWAY CATALOGUE")
        if model in SLOW_GENERATION_MODELS:
            notes.append("SLOW MODEL ON A SYNCHRONOUS ROLE")

        started = time.monotonic()
        try:
            reply = await client.chat(_PROBE, max_tokens=_PROBE_MAX_TOKENS)
            elapsed = time.monotonic() - started
            status = "ok"
            detail = f"{elapsed:6.2f}s  {reply.strip()[:40]!r}"
        except Exception as exc:
            elapsed = time.monotonic() - started
            status = "FAIL"
            detail = f"{elapsed:6.2f}s  {type(exc).__name__}: {exc}"
            failures += 1

        suffix = f"  [{'; '.join(notes)}]" if notes else ""
        print(f"{status:4}  {role:14} model={model:16} ({source}, {timeout:g}s)  {detail}{suffix}")

    print()
    if failures:
        # Non-zero so this can gate a deploy. A failing role does not break
        # Limen — it silently degrades to the deterministic path, which is
        # exactly why the failure has to be surfaced here instead.
        print(f"{failures}/{len(AGENT_ROLES)} roles unreachable — those roles will emit")
        print("`llm.fallback` and ship deterministic text instead of generated text.")
        return 1
    print(f"all {len(AGENT_ROLES)} roles answered")
    return 0
