"""Il client Anthropic con Haiku 5.5, che pensa sempre (#488)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from limen.agents.llm_factory import budget
from limen.agents.llm_factory.anthropic_factory import AnthropicChatClient
from limen.agents.llm_factory.base import ChatMessage, LlmFactoryError

pytest.importorskip("anthropic")


def _risposta(blocchi: list[Any], stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=blocchi,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=900),
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> AnthropicChatClient:
    async def _niente(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(budget, "verifica", _niente)
    monkeypatch.setattr(budget, "registra", _niente)
    return AnthropicChatClient(api_key=SecretStr("ak-test"), model="claude-haiku-5-5")


def _rispondi(client: AnthropicChatClient, risposta: Any) -> dict[str, Any]:
    chiamata: dict[str, Any] = {}

    async def _create(**kwargs: Any) -> Any:
        chiamata.update(kwargs)
        return risposta

    client._client = SimpleNamespace(messages=SimpleNamespace(create=_create))  # type: ignore[assignment]
    return chiamata


async def test_tetto_largo_e_sforzo_basso(client: AnthropicChatClient) -> None:
    pensiero = SimpleNamespace(type="thinking", thinking="")
    testo = SimpleNamespace(type="text", text="La Liguria è in allerta.")
    chiamata = _rispondi(client, _risposta([pensiero, testo]))
    out = await client.chat([ChatMessage(role="user", content="scrivi")])
    assert out == "La Liguria è in allerta."
    assert chiamata["max_tokens"] >= 8000
    assert chiamata["output_config"] == {"effort": "low"}


@pytest.mark.parametrize("stop_reason", ["max_tokens", "end_turn", "refusal"])
async def test_senza_testo_e_un_errore_non_un_testo_vuoto(
    client: AnthropicChatClient, stop_reason: str
) -> None:
    _rispondi(client, _risposta([SimpleNamespace(type="thinking", thinking="")], stop_reason))
    with pytest.raises(LlmFactoryError, match=stop_reason):
        await client.chat([ChatMessage(role="user", content="scrivi")])


async def test_testo_troncato_e_un_errore(client: AnthropicChatClient) -> None:
    _rispondi(client, _risposta([SimpleNamespace(type="text", text="La Lig")], "max_tokens"))
    with pytest.raises(LlmFactoryError):
        await client.chat([ChatMessage(role="user", content="scrivi")])
