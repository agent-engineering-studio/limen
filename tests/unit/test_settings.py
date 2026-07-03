"""Settings + LLM-provider precedence — pure unit tests."""

from __future__ import annotations

from typing import Any, cast

import pytest

from limen.config.settings import (
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


def test_llm_resolver_falls_back_to_ollama() -> None:
    s = _make_settings()
    assert resolve_provider(s).provider is LLMProvider.OLLAMA
