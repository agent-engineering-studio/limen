"""L'estensione MCP Events sul server ``limen-ops``, attraverso il protocollo (#371)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client
from mcp.shared.exceptions import MCPError
from mcp_types import Request, RequestParams
from pydantic import TypeAdapter

from limen.config.settings import get_settings
from limen.core import eventi
from limen.data.repos import eventi_repo
from limen.mcp import server

_DIZ: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


class _Lista(Request[RequestParams, Literal["events/list"]]):
    method: Literal["events/list"] = "events/list"
    params: RequestParams = RequestParams()


class _ParametriPoll(RequestParams):
    name: str
    arguments: dict[str, Any] | None = None
    cursor: str | None = None


class _Poll(Request[_ParametriPoll, Literal["events/poll"]]):
    method: Literal["events/poll"] = "events/poll"


@pytest.fixture
def con_eventi(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MCP__EVENTI", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_senza_flag_l_estensione_non_c_e(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP__EVENTI", raising=False)
    get_settings.cache_clear()
    async with Client(server._build_server()) as client:
        with pytest.raises(MCPError):
            await client.session.send_request(_Lista(), _DIZ)


async def test_lista_e_poll_attraverso_il_protocollo(
    con_eventi: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    chiesti: list[tuple[str, Any, Any]] = []

    async def _poll(nome: str, argomenti: Any, cursore: Any, **_: Any) -> dict[str, Any]:
        chiesti.append((nome, argomenti, cursore))
        if argomenti and "colore" in argomenti:
            raise eventi.ArgomentiNonValidiError("argomenti sconosciuti: colore")
        return {"events": [], "cursor": "c", "truncated": False, "hasMore": False}

    monkeypatch.setattr(eventi_repo, "poll", _poll)
    async with Client(server._build_server()) as client:
        capacita = client.server_capabilities
        assert capacita is not None
        assert eventi.IDENTIFICATORE in (capacita.extensions or {})
        lista = await client.session.send_request(_Lista(), _DIZ)
        assert [e["name"] for e in lista["events"]] == [
            eventi.ALLERTA,
            eventi.CAMBIO_CLASSE,
            eventi.NON_MISURATO,
        ]
        poll = await client.session.send_request(
            _Poll(params=_ParametriPoll(name=eventi.ALLERTA)), _DIZ
        )
        assert poll["cursor"] == "c"
        assert chiesti == [(eventi.ALLERTA, None, None)]
        with pytest.raises(MCPError) as ignoto:
            await client.session.send_request(_Poll(params=_ParametriPoll(name="x.y")), _DIZ)
        assert ignoto.value.error.code == eventi.NON_TROVATO
        with pytest.raises(MCPError) as storto:
            await client.session.send_request(
                _Poll(params=_ParametriPoll(name=eventi.ALLERTA, arguments={"colore": 1})),
                _DIZ,
            )
        assert storto.value.error.code == eventi.PARAMETRI_NON_VALIDI
