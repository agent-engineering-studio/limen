"""Pick the concrete :class:`LlmClientFactory` for the current process.

Precedence (identical in dev and prod, mirrors :mod:`limen.core.llm_resolver`):

1. Explicit ``LLM__PROVIDER`` override.
2. ``ANTHROPIC_API_KEY`` → Anthropic.
3. ``OPENAI_API_KEY`` → OpenAI.
4. Foundry credentials (Anthropic-on-Foundry or Azure-OpenAI-on-Foundry).
5. Otherwise → llama.cpp (the self-hosted inference server).

A cloud key always wins over the local engine unless ``LLM__PROVIDER`` is set
explicitly — so Claude is available but opt-in, selected by the mere presence
of ``ANTHROPIC_API_KEY``.

The fallback used to be Ollama. Deployments that relied on it implicitly must
now set ``LLM__PROVIDER=ollama``.

The resolver only **constructs** factories whose credentials/SDKs are
satisfied. That keeps the test path (Stub/Ollama) free of third-party
SDK imports.
"""

from __future__ import annotations

from limen.agents.llm_factory.anthropic_factory import AnthropicFactory
from limen.agents.llm_factory.base import LlmClientFactory, LlmFactoryError
from limen.agents.llm_factory.foundry_factory import FoundryFactory
from limen.agents.llm_factory.llamacpp_factory import LlamaCppFactory
from limen.agents.llm_factory.ollama_factory import OllamaFactory
from limen.agents.llm_factory.openai_factory import OpenAIFactory
from limen.config.settings import LLMProvider, Settings, get_settings
from limen.core.logging import get_logger

log = get_logger(__name__)


# Agent-role label (what the workflow passes to ``factory.create``) → the
# ``LLMModels`` field that configures it, i.e. the LLM__MODELS__* env var.
_ROLE_FIELDS: dict[str, str] = {
    "RiskAnalyst": "risk_analyst",
    "Briefing": "briefing",
    "Orchestrator": "orchestrator",
    "Scorer": "scorer",
    "Summarizer": "summarizer",
}


# The roles a factory can be asked for, in declaration order. Public so the
# `limen llm-check` command can probe every one without reaching into
# ``_ROLE_FIELDS``; :func:`role_models` is public for the same reason.
AGENT_ROLES: tuple[str, ...] = tuple(_ROLE_FIELDS)


def role_models(settings: Settings) -> dict[str, str]:
    """Map agent-role label → concrete model id from the LLMModels block."""
    m = settings.llm.models
    return {role: str(getattr(m, field)) for role, field in _ROLE_FIELDS.items()}


def _declared_role_models(settings: Settings) -> dict[str, str]:
    """The per-role map restricted to roles actually set in the environment.

    A per-role map *is* meaningful to the local engines now. Behind the LiteLLM
    gateway a model name is an arbitrary key in its ``model_list`` — ``fast``,
    ``chat``, ``extract`` — so this map is exactly how you stop one 4B model
    from having to serve both the Italian briefing and the JSON extraction.
    That was not true when the map could only hold Claude ids, which is why
    both local factories used to discard it.

    What is still true is that the :class:`LLMModels` *defaults* are Claude
    ids, and asking the gateway for ``claude-haiku-4-5`` is a 400, not a
    graceful fallback. Hence the filter: honour the roles the operator
    declared, and let every other role fall through to ``default_model``. A
    deployment that sets no LLM__MODELS__* keeps today's single-model
    behaviour; one that sets them gets real per-role routing.

    Do not go back to passing ``{}`` here — that silently discards the
    LLM__MODELS__* variables the compose file now sets.
    """
    declared = settings.llm.models.model_fields_set
    return {
        role: model
        for role, model in role_models(settings).items()
        if _ROLE_FIELDS[role] in declared
    }


def _build_anthropic(settings: Settings) -> AnthropicFactory:
    assert settings.anthropic_api_key is not None
    return AnthropicFactory(
        api_key=settings.anthropic_api_key,
        role_models=role_models(settings),
    )


def _build_openai(settings: Settings) -> OpenAIFactory:
    assert settings.openai_api_key is not None
    return OpenAIFactory(
        api_key=settings.openai_api_key,
        role_models=role_models(settings),
    )


def _build_foundry(settings: Settings) -> FoundryFactory:
    return FoundryFactory(
        role_models=role_models(settings),
        azure_endpoint=settings.azure_ai_endpoint,
        azure_api_key=settings.azure_ai_api_key,
        anthropic_endpoint=settings.anthropic_foundry_endpoint or settings.foundry_endpoint,
        anthropic_api_key=settings.anthropic_foundry_api_key or settings.foundry_api_key,
    )


def _build_ollama(settings: Settings) -> OllamaFactory:
    key = settings.llm.ollama_api_key
    # Same reasoning as llama.cpp: see :func:`_declared_role_models`. Ollama
    # has no gateway in front of it, so the declared names must be real Ollama
    # tags (``qwen3:4b``) rather than gateway aliases — but the mechanism is
    # identical, and leaving the two local factories inconsistent would just be
    # a trap for whoever configures Ollama next.
    return OllamaFactory(
        base_url=settings.llm.ollama_base_url,
        role_models=_declared_role_models(settings),
        default_model=settings.llm.ollama_model,
        api_key=key.get_secret_value() if key is not None else None,
        timeout_seconds=settings.llm.ollama_timeout_seconds,
    )


def _build_llamacpp(settings: Settings) -> LlamaCppFactory:
    key = settings.llm.llamacpp_api_key
    return LlamaCppFactory(
        base_url=settings.llm.llamacpp_base_url,
        role_models=_declared_role_models(settings),
        default_model=settings.llm.llamacpp_model,
        api_key=key.get_secret_value() if key is not None else None,
        timeout_seconds=settings.llm.llamacpp_timeout_seconds,
        role_timeouts=dict(settings.llm.llamacpp_role_timeout_seconds),
    )


def _sdk_available(module: str) -> bool:
    """True when ``module`` can be imported (the provider's SDK is installed)."""
    import importlib.util

    return importlib.util.find_spec(module) is not None


def _has_anthropic(settings: Settings) -> bool:
    return settings.anthropic_api_key is not None


def _has_openai(settings: Settings) -> bool:
    return settings.openai_api_key is not None


def _has_foundry(settings: Settings) -> bool:
    return (settings.azure_ai_endpoint is not None and settings.azure_ai_api_key is not None) or (
        (settings.anthropic_foundry_endpoint or settings.foundry_endpoint) is not None
        and (settings.anthropic_foundry_api_key or settings.foundry_api_key) is not None
    )


def resolve_llm_factory(settings: Settings | None = None) -> LlmClientFactory:
    """Return the appropriate factory according to the precedence above."""
    s = settings or get_settings()
    explicit = s.llm.provider

    if explicit is not None:
        log.info("llm.resolver.explicit", provider=explicit.value)
        if explicit is LLMProvider.ANTHROPIC:
            if not _has_anthropic(s):
                raise LlmFactoryError("LLM__PROVIDER=anthropic but ANTHROPIC_API_KEY is unset")
            return _build_anthropic(s)
        if explicit is LLMProvider.OPENAI:
            if not _has_openai(s):
                raise LlmFactoryError("LLM__PROVIDER=openai but OPENAI_API_KEY is unset")
            return _build_openai(s)
        if explicit is LLMProvider.FOUNDRY:
            if not _has_foundry(s):
                raise LlmFactoryError(
                    "LLM__PROVIDER=foundry but no Foundry endpoint+key pair is set"
                )
            return _build_foundry(s)
        if explicit is LLMProvider.OLLAMA:
            return _build_ollama(s)
        # explicit llama.cpp or anything else
        return _build_llamacpp(s)

    # Autodetect: a cloud key selects its provider only if the SDK is actually
    # installed. Otherwise fall through — in production the image ships without
    # the `agents` group and Ollama (httpx-only, no SDK) is the intended engine,
    # so a leaked ANTHROPIC_API_KEY must not crash the non-authoritative LLM path.
    if _has_anthropic(s):
        if _sdk_available("anthropic"):
            log.info("llm.resolver.autodetect", provider="anthropic")
            return _build_anthropic(s)
        log.warning("llm.resolver.sdk_missing", provider="anthropic", note="agents group")
    if _has_openai(s):
        if _sdk_available("openai"):
            log.info("llm.resolver.autodetect", provider="openai")
            return _build_openai(s)
        log.warning("llm.resolver.sdk_missing", provider="openai", note="agents group")
    if _has_foundry(s):
        log.info("llm.resolver.autodetect", provider="foundry")
        return _build_foundry(s)

    log.info("llm.resolver.fallback", provider="llamacpp", base_url=s.llm.llamacpp_base_url)
    return _build_llamacpp(s)
