"""Settings + LLM-provider precedence — pure unit tests."""

from __future__ import annotations

from typing import Any, cast

import pytest

from limen.config.settings import (
    SLOW_GENERATION_MODELS,
    LLMProvider,
    ObjectStoreBackend,
    SchedulerBackend,
    Settings,
)
from limen.core.llm_resolver import resolve_provider


def _make_settings(**overrides: object) -> Settings:
    # Build a Settings instance with defaults and no .env file picked up.
    # Cast through Any: pydantic-settings' `_env_file` kwarg coexists with
    # arbitrary field overrides, which its typed __init__ signature rejects.
    return cast(Settings, cast(Any, Settings)(_env_file=None, **overrides))


def test_defaults_select_filesystem_and_apscheduler() -> None:
    s = _make_settings()
    assert s.object_store.backend is ObjectStoreBackend.FILESYSTEM
    assert s.scheduler.cache_cleanup is SchedulerBackend.APSCHEDULER


def test_db_pool_validation_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="POOL_MAX_SIZE"):
        _make_settings(db={"pool_min_size": 10, "pool_max_size": 5})


def test_llm_resolver_explicit_override_wins() -> None:
    s = _make_settings(
        llm={"provider": "ollama"},
        anthropic_api_key="ak-xxx",
    )
    resolved = resolve_provider(s)
    assert resolved.provider is LLMProvider.OLLAMA


def test_llm_resolver_prefers_anthropic_over_openai() -> None:
    s = _make_settings(anthropic_api_key="a", openai_api_key="o")
    assert resolve_provider(s).provider is LLMProvider.ANTHROPIC


def test_llm_resolver_falls_back_to_openai_when_no_anthropic() -> None:
    s = _make_settings(openai_api_key="o")
    assert resolve_provider(s).provider is LLMProvider.OPENAI


def test_llm_resolver_falls_back_to_foundry() -> None:
    s = _make_settings(foundry_endpoint="https://foundry", foundry_api_key="fk")
    assert resolve_provider(s).provider is LLMProvider.FOUNDRY


def test_llm_resolver_falls_back_to_llamacpp() -> None:
    """No credentials → the self-hosted llama.cpp server, not Ollama."""
    s = _make_settings()
    assert resolve_provider(s).provider is LLMProvider.LLAMACPP


def test_llm_resolver_ollama_still_selectable_explicitly() -> None:
    """The fallback moved to llama.cpp, so Ollama now needs to be declared."""
    s = _make_settings(llm={"provider": "ollama"})
    assert resolve_provider(s).provider is LLMProvider.OLLAMA


@pytest.mark.parametrize("slow_model", sorted(SLOW_GENERATION_MODELS))
def test_slow_model_on_a_sync_role_refuses_to_start(slow_model: str) -> None:
    """Un ruolo sincrono puntato su un modello che genera in decine di minuti
    deve essere un rifiuto all'avvio, non un timeout del chiamante che degrada
    in silenzio al testo deterministico.

    Il ruolo qui è `risk_analyst` e non più `briefing`: dopo #78 il briefing è
    l'unico consumatore asincrono, mentre il RiskAnalyst resta su MCP e sui
    percorsi HTTP."""
    with pytest.raises(ValueError, match=r"synchronous"):
        _make_settings(llm={"models": {"risk_analyst": slow_model}})


@pytest.mark.parametrize("slow_model", sorted(SLOW_GENERATION_MODELS))
def test_slow_model_is_allowed_on_the_briefing_role(slow_model: str) -> None:
    """Dopo #78 il briefing non gira più dentro il tick orario: lo scrive
    `briefing_enrichment` su righe già persistite, una regione alla volta, e
    nessuno lo aspetta — la mappa mostra il testo deterministico finché non
    arriva. Lì un modello lento è lento, non rotto."""
    s = _make_settings(llm={"models": {"briefing": slow_model}})
    assert s.llm.models.briefing == slow_model


def test_slow_model_check_covers_undeclared_roles_too() -> None:
    """LLMModels allows extra keys, so a future role name must not slip past."""
    with pytest.raises(ValueError, match=r"LLM__MODELS__REPORT"):
        _make_settings(llm={"models": {"report": "quality-local"}})


def test_fast_gateway_models_are_accepted_on_sync_roles() -> None:
    s = _make_settings(llm={"models": {"briefing": "chat", "risk_analyst": "extract"}})
    assert s.llm.models.briefing == "chat"
    assert s.llm.models.risk_analyst == "extract"


def test_llamacpp_role_timeout_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match=r"positive ceiling"):
        _make_settings(llm={"llamacpp_role_timeout_seconds": {"Briefing": 0.0}})
