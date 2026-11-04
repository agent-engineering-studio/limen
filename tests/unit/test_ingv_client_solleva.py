"""`solleva=True` separa un guasto di INGV da un risultato vuoto (Codex su #310).

Il backtest lo chiede; lo sweep no, e degrada come prima. Niente 5xx qui:
tenacity li riprova con backoff, e il test durerebbe minuti.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from limen.integrations.ingv.shakemap_client import (
    FDSN_EVENT_URL,
    IngvHttpClient,
    IngvNonDisponibileError,
    shakemap_grid_url,
)

FINESTRA = {
    "bbox": (12.0, 42.0, 14.0, 43.5),
    "start": datetime(2016, 8, 20, tzinfo=UTC),
    "end": datetime(2016, 9, 1, tzinfo=UTC),
}


async def _eventi(risposta: httpx.Response, *, solleva: bool) -> list[object]:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(FDSN_EVENT_URL).mock(return_value=risposta)
            return list(
                await IngvHttpClient(http_client=http).fetch_events(**FINESTRA, solleva=solleva)
            )


async def _griglia(risposta: httpx.Response, *, solleva: bool) -> bytes | None:
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(shakemap_grid_url("7073641")).mock(return_value=risposta)
            return await IngvHttpClient(http_client=http).fetch_shakemap_grid(
                "7073641", solleva=solleva
            )


@pytest.mark.parametrize(
    "risposta",
    [httpx.Response(400), httpx.Response(200, content=b"<html>non json</html>")],
    ids=["http_400", "json_rotto"],
)
async def test_un_catalogo_guasto(risposta: httpx.Response) -> None:
    assert await _eventi(risposta, solleva=False) == []
    with pytest.raises(IngvNonDisponibileError):
        await _eventi(risposta, solleva=True)


async def test_una_finestra_vuota_resta_vuota_anche_se_si_solleva() -> None:
    assert await _eventi(httpx.Response(204), solleva=True) == []


async def test_una_shakemap_che_non_esiste_non_e_un_guasto() -> None:
    assert await _griglia(httpx.Response(404), solleva=True) is None


async def test_una_shakemap_rifiutata_e_un_guasto() -> None:
    assert await _griglia(httpx.Response(403), solleva=False) is None
    with pytest.raises(IngvNonDisponibileError):
        await _griglia(httpx.Response(403), solleva=True)


async def test_info_json_della_mappa() -> None:
    info = {
        "input": {"event_information": {"event_id": "7073641"}},
        "output": {},
        "processing": {"shakemap_versions": {"map_version": 4, "map_status": "automatic"}},
    }
    async with httpx.AsyncClient() as http:
        with respx.mock:
            respx.get(shakemap_grid_url("7073641").replace("grid.xml", "info.json")).mock(
                return_value=httpx.Response(200, json=info)
            )
            letta = await IngvHttpClient(http_client=http).fetch_info("7073641")
    assert letta is not None and (letta.version, letta.map_status) == (4, "automatic")


async def test_info_json_rifiutato() -> None:
    async def info(*, solleva: bool) -> object:
        async with httpx.AsyncClient() as http:
            with respx.mock:
                respx.get(url__regex=r".*/info\.json").mock(return_value=httpx.Response(403))
                return await IngvHttpClient(http_client=http).fetch_info("1", solleva=solleva)

    assert await info(solleva=False) is None
    with pytest.raises(IngvNonDisponibileError):
        await info(solleva=True)
