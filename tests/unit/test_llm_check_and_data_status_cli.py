"""`limen llm-check` e `limen data-status`: i due comandi diagnostici (#116).

Entrambi esistono per dire a un operatore la cosa che il sistema altrimenti
nasconde. `llm-check` esce non-zero se un ruolo non risponde, perché un ruolo
rotto non rompe Limen: degrada in silenzio al testo deterministico, ed è
proprio per questo che il guasto va reso visibile qui. `data-status` risponde
a "perché la mappa è uniforme?".
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

from limen.cli import data_status, llm_check
from limen.config.settings import LLMProvider
from limen.integrations._http import SharedHttpClient

_GATEWAY = "http://host.docker.internal:8091"


@pytest.fixture(autouse=True)
async def _close_http():
    yield
    await SharedHttpClient.aclose()


class _Client:
    def __init__(self, model: str, reply: str | Exception) -> None:
        self.model = model
        self.timeout_seconds = 30.0
        self._reply = reply

    async def chat(self, _messages: Any, *, max_tokens: int) -> str:
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def _llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider: LLMProvider,
    clients: dict[str, _Client],
    declared: set[str],
) -> None:
    key = SimpleNamespace(get_secret_value=lambda: "sk-locale")
    settings = SimpleNamespace(
        llm=SimpleNamespace(
            provider=provider,
            llamacpp_base_url=_GATEWAY,
            ollama_base_url="http://host.docker.internal:11434",
            llamacpp_api_key=key,
            ollama_api_key=None,
            models=SimpleNamespace(model_fields_set=declared),
        )
    )
    factory = SimpleNamespace(provider=provider.value, create=lambda role: clients[role])
    monkeypatch.setattr(llm_check, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_check, "resolve_llm_factory", lambda _s: factory)
    monkeypatch.setattr(llm_check, "role_models", lambda _s: dict.fromkeys(clients, "?"))
    monkeypatch.setattr(llm_check, "AGENT_ROLES", tuple(clients))


@respx.mock
async def test_every_role_answers(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    route = respx.get(f"{_GATEWAY}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "fast-local"}, {"id": "quality"}]})
    )
    _llm(
        monkeypatch,
        provider=LLMProvider.LLAMACPP,
        clients={
            "risk_analyst": _Client("fast-local", "ok"),
            "briefing": _Client("quality", "ok"),
        },
        declared={"risk_analyst"},
    )

    assert await llm_check.run() == 0

    out = capsys.readouterr().out
    assert route.calls.last.request.headers["Authorization"] == "Bearer sk-locale"
    assert "models:   fast-local, quality" in out
    assert "(declared, 30s)" in out and "(fallback, 30s)" in out
    assert "all 2 roles answered" in out
    assert "NOT IN GATEWAY CATALOGUE" not in out


@respx.mock
async def test_a_failing_role_exits_non_zero_and_is_flagged(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Un modello che il gateway non conosce, e un modello lento su un ruolo
    sincrono: due guasti che a runtime sarebbero solo testo deterministico."""
    respx.get(f"{_GATEWAY}/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "fast-local"}]})
    )
    _llm(
        monkeypatch,
        provider=LLMProvider.LLAMACPP,
        clients={
            "risk_analyst": _Client("quality-local", TimeoutError("nessuna risposta")),
            "briefing": _Client("fast-local", "ok"),
        },
        declared=set(),
    )

    assert await llm_check.run() == 1

    out = capsys.readouterr().out
    assert "FAIL  risk_analyst" in out
    assert "TimeoutError: nessuna risposta" in out
    assert "NOT IN GATEWAY CATALOGUE; SLOW MODEL ON A SYNCHRONOUS ROLE" in out
    assert "1/2 roles unreachable" in out


@respx.mock
async def test_an_unreachable_gateway_is_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    respx.get(f"{_GATEWAY}/v1/models").mock(return_value=httpx.Response(503))
    _llm(
        monkeypatch,
        provider=LLMProvider.LLAMACPP,
        clients={"briefing": _Client("fast-local", RuntimeError("gateway giù"))},
        declared=set(),
    )
    assert await llm_check.run() == 1
    out = capsys.readouterr().out
    assert "UNREACHABLE" in out
    # Senza catalogo non si può dire "non è nel catalogo": niente falso allarme.
    assert "NOT IN GATEWAY CATALOGUE" not in out


async def test_a_cloud_provider_has_no_catalogue_to_probe(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    _llm(
        monkeypatch,
        provider=LLMProvider.ANTHROPIC,
        clients={"briefing": _Client("claude-sonnet-5", "ok")},
        declared={"briefing"},
    )
    assert await llm_check.run() == 0
    out = capsys.readouterr().out
    assert "base_url" not in out
    assert "provider: anthropic" in out


def test_base_url_per_provider() -> None:
    llm = SimpleNamespace(llamacpp_base_url="http://a", ollama_base_url="http://b")
    for provider, expected in (
        (LLMProvider.LLAMACPP, "http://a"),
        (LLMProvider.OLLAMA, "http://b"),
        (LLMProvider.OPENAI, None),
    ):
        llm.provider = provider
        assert llm_check._base_url(SimpleNamespace(llm=llm)) == expected


@respx.mock
async def test_a_malformed_catalogue_counts_as_unreachable() -> None:
    respx.get(f"{_GATEWAY}/v1/models").mock(return_value=httpx.Response(200, json={"oggetti": []}))
    assert await llm_check._catalogue(_GATEWAY, None) is None


# ---------------------------------------------------------------------------
# data-status
# ---------------------------------------------------------------------------
def _db(monkeypatch: pytest.MonkeyPatch, counts: dict[str, int]) -> None:
    class _Conn:
        async def fetchval(self, sql: str) -> int:
            for fragment, value in counts.items():
                if fragment in sql:
                    return value
            raise AssertionError(f"query non prevista: {sql}")

    @asynccontextmanager
    async def _pool():
        yield

    @asynccontextmanager
    async def _acquire():
        yield _Conn()

    monkeypatch.setattr(data_status, "lifespan_pool", _pool)
    monkeypatch.setattr(data_status, "acquire", _acquire)


async def test_data_status_on_an_unseeded_database(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    _db(monkeypatch, {"count(*) FROM cell_static_factors": 0, "count(*) FROM aoi": 0})
    assert await data_status.run() == 0
    assert "esegui prima `limen seed`" in capsys.readouterr().out


async def test_data_status_names_what_each_hazard_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Le frane hanno tutto, l'alluvione no: il rapporto deve dire quale layer
    manca, quale variabile lo abilita e con che comando si procura."""
    loaded = {"iffi_density_500", "pai_class_norm", "slope_deg", "litho_weight", "landuse_code"}
    counts = {"count(*) FROM cell_static_factors": 10353, "count(*) FROM aoi": 2}
    for layer in data_status.LAYERS:
        counts[f"count({layer.column})"] = 10353 if layer.column in loaded else 0
    counts["count(*) FROM fire_perimeters"] = 515
    _db(monkeypatch, counts)
    monkeypatch.delenv("LIMEN_IMPERVIOUSNESS_RASTER", raising=False)
    monkeypatch.delenv("GEOSERVER_SOURCE__DB_DSN", raising=False)
    monkeypatch.setenv("LIMEN_OSM_ROADS", "/dati/strade.gpkg")

    assert await data_status.run() == 0

    out = capsys.readouterr().out
    assert "10.353 celle in 2 AOI" in out
    assert "515" in out
    assert "frana       tutto presente" in out
    assert "incendio    tutto presente" in out
    assert "alluvione   manca: pericolosità idraulica ISPRA, suolo impermeabilizzato (CLMS)" in out
    assert "LIMEN_IMPERVIOUSNESS_RASTER   → make imperviousness-data" in out
    assert "  GEOSERVER_SOURCE__DB_DSN\n" in out
    # Impostata ma vuota: il problema non è la variabile, e non va elencata.
    assert "LIMEN_OSM_ROADS\n" not in out.split("Variabili non impostate")[1]


def test_bar_is_proportional() -> None:
    assert data_status._bar(0.0) == "." * 20
    assert data_status._bar(0.5) == "#" * 10 + "." * 10
    assert data_status._bar(1.0, width=4) == "####"
