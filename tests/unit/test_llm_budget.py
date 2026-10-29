"""Il tetto mensile su Claude: chi lo controlla, chi lo paga, cosa si vede."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx
from fastapi import Response

from limen.agents.llm_factory import budget
from limen.agents.llm_factory.base import ChatMessage
from limen.agents.llm_factory.llamacpp_factory import LlamaCppChatClient
from limen.api.endpoints import status
from limen.data.repos import spesa_llm_repo
from limen.data.repos.spesa_llm_repo import Consumo
from limen.integrations._http import SharedHttpClient

_GATEWAY = "http://gateway.test:8091"
_MSG = [ChatMessage(role="user", content="ciao")]


class Registro:
    """Il repo della spesa in memoria."""

    def __init__(self) -> None:
        self.righe: list[dict[str, Any]] = []
        self.spesa = Decimal(0)

    def spende(self, valore: str) -> None:
        self.spesa = Decimal(valore)
        budget._cache = None

    async def spesa_del_mese(self) -> Decimal:
        return self.spesa

    async def registra(self, **kw: Any) -> None:
        self.righe.append(kw)


@pytest.fixture
def registro(monkeypatch: pytest.MonkeyPatch) -> Registro:
    r = Registro()
    monkeypatch.setattr(budget, "_cache", None)
    monkeypatch.setattr(spesa_llm_repo, "spesa_del_mese", r.spesa_del_mese)
    monkeypatch.setattr(spesa_llm_repo, "registra", r.registra)
    return r


async def test_sotto_il_tetto_la_chiamata_parte(registro: Registro) -> None:
    registro.spende("9.99")
    await budget.verifica("claude-haiku-5-5")


async def test_al_tetto_la_chiamata_si_ferma(registro: Registro) -> None:
    registro.spende("10")
    with pytest.raises(budget.BudgetSuperatoError, match="tetto mensile di 10 \\$"):
        await budget.verifica("claude-haiku-5-5")


async def test_senza_database_il_tetto_resta_chiuso(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _rotto() -> Decimal:
        raise RuntimeError("DB pool not initialized")

    monkeypatch.setattr(budget, "_cache", None)
    monkeypatch.setattr(spesa_llm_repo, "spesa_del_mese", _rotto)
    with pytest.raises(budget.BudgetSuperatoError, match="non leggibile"):
        await budget.verifica("claude-haiku-5-5")


async def test_la_spesa_registrata_conta_subito(registro: Registro) -> None:
    registro.spende("9.9")
    await budget.spesa_del_mese()
    # 1M token d'ingresso di Haiku a listino: 0,10 $, e il tetto è raggiunto
    # senza aspettare che la cache scada.
    costo = await budget.registra(
        origine="Briefing", modello="claude-haiku-5-5", input_tokens=1_000_000, output_tokens=0
    )
    assert costo == Decimal("0.1")
    assert await budget.superato()


async def test_un_modello_locale_costa_zero(registro: Registro) -> None:
    costo = await budget.registra(
        origine="Briefing", modello="chat-8b", input_tokens=5000, output_tokens=500
    )
    assert costo == 0
    assert registro.righe[0]["costo_usd"] == 0 and registro.righe[0]["input_tokens"] == 5000


async def test_una_registrazione_fallita_non_perde_la_risposta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _rotto(**_kw: Any) -> None:
        raise RuntimeError("db giù")

    monkeypatch.setattr(spesa_llm_repo, "registra", _rotto)
    costo = await budget.registra(
        origine="Briefing", modello="claude-haiku-5-5", input_tokens=10, output_tokens=10
    )
    assert costo > 0


@pytest.fixture
async def gateway() -> Any:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


def _risposta(modello_effettivo: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "x",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 200},
        },
        headers={"x-litellm-model-name": modello_effettivo},
    )


@respx.mock
async def test_fast_cloud_oltre_il_tetto_non_chiama_il_gateway(
    registro: Registro, gateway: Any
) -> None:
    registro.spende("10")
    route = respx.post(f"{_GATEWAY}/v1/chat/completions").mock(
        return_value=_risposta("anthropic/claude-haiku-5-5")
    )
    client = LlamaCppChatClient(base_url=_GATEWAY, model="fast-cloud", ruolo="Briefing")
    with pytest.raises(budget.BudgetSuperatoError):
        await client.chat(_MSG)
    assert not route.called
    assert registro.righe == []


@respx.mock
async def test_un_modello_locale_passa_anche_oltre_il_tetto(
    registro: Registro, gateway: Any
) -> None:
    registro.spende("10")
    respx.post(f"{_GATEWAY}/v1/chat/completions").mock(return_value=_risposta("openai/chat-8b"))
    client = LlamaCppChatClient(base_url=_GATEWAY, model="chat", ruolo="Briefing")
    assert await client.chat(_MSG) == "ok"
    assert registro.righe[0]["modello"] == "chat-8b" and registro.righe[0]["costo_usd"] == 0


@respx.mock
async def test_la_spesa_va_su_chi_ha_risposto_davvero(registro: Registro, gateway: Any) -> None:
    respx.post(f"{_GATEWAY}/v1/chat/completions").mock(
        return_value=_risposta("anthropic/claude-haiku-5-5")
    )
    client = LlamaCppChatClient(base_url=_GATEWAY, model="fast-cloud", ruolo="RiskAnalyst")
    await client.chat(_MSG)
    riga = registro.righe[0]
    assert riga["origine"] == "RiskAnalyst" and riga["modello"] == "claude-haiku-5-5"
    # 1000 token a 0,10 $ e 200 a 0,50 $ per milione.
    assert riga["costo_usd"] == Decimal("0.0002")


async def test_la_pagina_pubblica_mostra_i_token_e_non_i_dollari(
    monkeypatch: pytest.MonkeyPatch, registro: Registro
) -> None:
    registro.spende("10")
    consumo = Consumo(
        chiave="claude-haiku-5-5",
        richieste=3,
        input_tokens=3000,
        output_tokens=600,
        costo_usd=Decimal("7.5"),
    )

    async def _consumi(per: str) -> list[Consumo]:
        return [consumo] if per == "modello" else []

    monkeypatch.setattr(spesa_llm_repo, "consumi_del_mese", _consumi)
    out = await status.llm_status(Response())
    assert out.in_pausa and out.ripresa is not None and out.ripresa.day == 1
    assert (out.richieste, out.input_tokens, out.output_tokens) == (3, 3000, 600)
    assert "costo" not in out.model_dump_json() and "7.5" not in out.model_dump_json()


def test_il_primo_del_mese_dopo_dicembre_e_gennaio() -> None:
    assert spesa_llm_repo.primo_del_mese_prossimo(date(2026, 12, 31)) == date(2027, 1, 1)
    assert spesa_llm_repo.primo_del_mese_prossimo(date(2026, 10, 29)) == date(2026, 11, 1)
