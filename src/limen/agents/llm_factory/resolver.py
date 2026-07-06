"""Pick the concrete :class:`LlmClientFactory` for the current process.

Precedence (identical in dev and prod, mirrors :mod:`limen.core.llm_resolver`):

1. Explicit ``LLM__PROVIDER`` override.
2. ``ANTHROPIC_API_KEY`` → Anthropic.
3. ``OPENAI_API_KEY`` → OpenAI.
4. Foundry credentials (Anthropic-on-Foundry or Azure-OpenAI-on-Foundry).
5. Otherwise → Ollama.

A cloud key always wins over Ollama unless ``LLM__PROVIDER=ollama`` is set
explicitly.

The resolver only **constructs** factories whose credentials/SDKs are
satisfied. That keeps the test path (Stub/Ollama) free of third-party
SDK imports.
"""

from __future__ import annotations

from limen.agents.llm_factory.anthropic_factory import AnthropicFactory
from limen.agents.llm_factory.base import LlmClientFactory, LlmFactoryError
from limen.agents.llm_factory.foundry_factory import FoundryFactory
from limen.agents.llm_factory.ollama_factory import OllamaFactory
from limen.agents.llm_factory.openai_factory import OpenAIFactory
from limen.config.settings import LLMProvider, Settings, get_settings
from limen.core.logging import get_logger

log = get_logger(__name__)


def _role_models(settings: Settings) -> dict[str, str]:
    """Map agent-role label → concrete model id from the LLMModels block."""
    m = settings.llm.models
    return {
        "RiskAnalyst": m.risk_analyst,
        "Briefing": m.briefing,
        "Orchestrator": m.orchestrator,
        "Scorer": m.scorer,
        "Summarizer": m.summarizer,
    }


def _build_anthropic(settings: Settings) -> AnthropicFactory:
    assert settings.anthropic_api_key is not None
    return AnthropicFactory(
        api_key=settings.anthropic_api_key,
        role_models=_role_models(settings),
    )


def _build_openai(settings: Settings) -> OpenAIFactory:
    assert settings.openai_api_key is not None
    return OpenAIFactory(
        api_key=settings.openai_api_key,
        role_models=_role_models(settings),
    )


def _build_foundry(settings: Settings) -> FoundryFactory:
    return FoundryFactory(
        role_models=_role_models(settings),
        azure_endpoint=settings.azure_ai_endpoint,
        azure_api_key=settings.azure_ai_api_key,
        anthropic_endpoint=settings.anthropic_foundry_endpoint or settings.foundry_endpoint,
        anthropic_api_key=settings.anthropic_foundry_api_key or settings.foundry_api_key,
    )


def _build_ollama(settings: Settings) -> OllamaFactory:
    key = settings.llm.ollama_api_key
    # Ignore the per-role map (Claude ids Ollama can't serve) and use the
    # single configured Ollama model for every role.
    return OllamaFactory(
        base_url=settings.llm.ollama_base_url,
        role_models={},
        default_model=settings.llm.ollama_model,
        api_key=key.get_secret_value() if key is not None else None,
        timeout_seconds=settings.llm.ollama_timeout_seconds,
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
        # explicit Ollama or anything else
        return _build_ollama(s)

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

    log.info("llm.resolver.fallback", provider="ollama", base_url=s.llm.ollama_base_url)
    return _build_ollama(s)
