"""L'estensione MCP Events sul server ``limen-ops`` (#371), solo poll.

Protocollo e basta: il catalogo e i payload stanno in ``core/eventi.py``, le
query a cursore in ``data/repos/eventi_repo.py``. Si registra solo con
``MCP__EVENTI=true``: la specifica è una bozza, e se cambia questo file si
butta senza toccare altro.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastmcp.server.extensions import MethodBinding, ServerExtension
from mcp.server.context import ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp_types import RequestParams
from pydantic import Field

from limen.core.eventi import (
    IDENTIFICATORE,
    NOMI,
    NON_TROVATO,
    PARAMETRI_NON_VALIDI,
    ArgomentiNonValidiError,
    catalogo,
)
from limen.data.repos import eventi_repo


class ParametriLista(RequestParams):
    cursor: str | None = None


class ParametriPoll(RequestParams):
    name: str
    arguments: dict[str, Any] | None = None
    cursor: str | None = None
    max_age_ms: int | None = Field(default=None, alias="maxAgeMs", ge=0)
    max_events: int | None = Field(default=None, alias="maxEvents", ge=1)


async def _lista(_ctx: ServerRequestContext[Any, Any], _p: ParametriLista) -> dict[str, Any]:
    return {"events": catalogo()}


async def _poll(_ctx: ServerRequestContext[Any, Any], p: ParametriPoll) -> dict[str, Any]:
    if p.name not in NOMI:
        raise MCPError(NON_TROVATO, "NotFound", {"kind": "event", "name": p.name})
    try:
        return await eventi_repo.poll(
            p.name, p.arguments, p.cursor, max_age_ms=p.max_age_ms, max_events=p.max_events
        )
    except ArgomentiNonValidiError as exc:
        raise MCPError(PARAMETRI_NON_VALIDI, "InvalidParams", str(exc)) from exc


class EventiLimen(ServerExtension):
    """``events/list`` + ``events/poll``; push e webhook non sono offerti."""

    identifier = IDENTIFICATORE

    def methods(self) -> Sequence[MethodBinding]:
        return (
            MethodBinding("events/list", ParametriLista, _lista),
            MethodBinding("events/poll", ParametriPoll, _poll),
        )


__all__ = ["EventiLimen"]
