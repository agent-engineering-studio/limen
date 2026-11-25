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


def test_llm_resolver_falls_back_to_llamacpp() -> None:
    """No credentials → the self-hosted llama.cpp server, not Ollama."""
    s = _make_settings()
    assert resolve_provider(s).provider is LLMProvider.LLAMACPP


def test_llm_resolver_ollama_still_selectable_explicitly() -> None:
    """The fallback moved to llama.cpp, so Ollama now needs to be declared."""
    s = _make_settings(llm={"provider": "ollama"})
    assert resolve_provider(s).provider is LLMProvider.OLLAMA


def test_fast_gateway_models_are_accepted_on_sync_roles() -> None:
    s = _make_settings(llm={"models": {"briefing": "chat", "risk_analyst": "extract"}})
    assert s.llm.models.briefing == "chat"
    assert s.llm.models.risk_analyst == "extract"


def test_llamacpp_role_timeout_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match=r"positive ceiling"):
        _make_settings(llm={"llamacpp_role_timeout_seconds": {"Briefing": 0.0}})


def test_senza_url_pubblico_niente_broker_ne_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """#517: nessun default verso il server di un'altra installazione."""
    monkeypatch.delenv("PUBBLICO__URL", raising=False)
    s = _make_settings()
    assert s.pubblico.host is None
    assert s.iot.cittadini.registrazione.broker_pubblico == ""
    assert s.iot.cittadini.registrazione.webhook_ttn_pubblico == ""
    assert not _make_settings(
        iot={"cittadini": {"registrazione": {"aperta": True}}}
    ).iot.cittadini.registrazione.disponibile


@pytest.mark.parametrize(
    "url", ["https://limen.example.org", "https://Limen.Example.org:443/", "limen.example.org"]
)
def test_broker_e_webhook_si_ricavano_dall_url_pubblico(url: str) -> None:
    s = _make_settings(pubblico={"url": url})
    r = s.iot.cittadini.registrazione
    assert r.broker_pubblico == "mqtts://limen.example.org:8883"
    assert r.webhook_ttn_pubblico == "https://limen.example.org/sensori/v2/ttn"


def test_url_pubblico_dall_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBBLICO__URL", "https://rischio.example.it")
    s = _make_settings(iot={"cittadini": {"registrazione": {"aperta": True}}})
    assert s.iot.cittadini.registrazione.broker_pubblico == "mqtts://rischio.example.it:8883"
    assert s.iot.cittadini.registrazione.disponibile


def test_broker_e_webhook_espliciti_vincono_sull_url() -> None:
    s = _make_settings(
        pubblico={"url": "https://limen.example.org"},
        iot={
            "cittadini": {
                "registrazione": {
                    "broker_pubblico": "mqtts://sensori.example.org:8883",
                    "webhook_ttn_pubblico": "https://ttn.example.org/hook",
                }
            }
        },
    )
    r = s.iot.cittadini.registrazione
    assert r.broker_pubblico == "mqtts://sensori.example.org:8883"
    assert r.webhook_ttn_pubblico == "https://ttn.example.org/hook"


@pytest.mark.parametrize(
    ("nome", "leggi"),
    [
        ("EGMS_SERVICE_KEY", lambda s: s.egms.service_key.get_secret_value()),
        ("EGMS__SERVICE_KEY", lambda s: s.egms.service_key.get_secret_value()),
        ("EGMS_SERVICE_KEY_FILE", lambda s: s.egms.service_key_file),
        ("EGMS__SERVICE_KEY_FILE", lambda s: s.egms.service_key_file),
        ("FIRMS_MAP_KEY", lambda s: s.firms.map_key.get_secret_value()),
        ("FIRMS__MAP_KEY", lambda s: s.firms.map_key.get_secret_value()),
    ],
)
def test_le_chiavi_col_nome_della_libreria_e_con_quello_di_prima(
    monkeypatch: pytest.MonkeyPatch, nome: str, leggi: Any
) -> None:
    for v in (
        "EGMS_SERVICE_KEY",
        "EGMS__SERVICE_KEY",
        "EGMS_SERVICE_KEY_FILE",
        "EGMS__SERVICE_KEY_FILE",
        "FIRMS_MAP_KEY",
        "FIRMS__MAP_KEY",
    ):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv(nome, "valore")
    assert leggi(_make_settings()) == "valore"


def test_il_nome_della_libreria_vince(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRMS__MAP_KEY", "vecchia")
    monkeypatch.setenv("FIRMS_MAP_KEY", "nuova")
    s = _make_settings()
    assert s.firms.map_key is not None and s.firms.map_key.get_secret_value() == "nuova"


def test_le_tile_egms_stanno_nella_cartella_della_libreria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EGMS__CARTELLA", raising=False)
    monkeypatch.setenv("DATA_ROOT", "/dati")
    assert _make_settings().egms.cartella == "/dati/egms-client"
