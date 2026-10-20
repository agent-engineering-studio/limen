"""Il listener dell'ingresso HTTP (#265): parte su una porta vera, risponde, e
lascia al worker i suoi segnali."""

from __future__ import annotations

import asyncio
import contextlib
import signal
import socket
from datetime import UTC, datetime
from typing import Any

import httpx

from limen.config.settings import IotCittadiniSettings
from limen.integrations.iot.ingresso_http import servi


def _porta_libera() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _gestisci(**_: Any) -> str:
    raise AssertionError("una richiesta senza firma non arriva alla pipeline")


async def test_listener_risponde_e_non_tocca_sigterm() -> None:
    prima = signal.getsignal(signal.SIGTERM)
    c = IotCittadiniSettings(http_attivo=True, http_porta=_porta_libera())
    task = asyncio.create_task(servi(_gestisci, c, adesso=lambda: datetime.now(UTC)))
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(50):
                try:
                    risposta = await client.post(
                        f"http://127.0.0.1:{c.http_porta}/sensori/v2/pluvio-matera-01/obs",
                        content=b"[]",
                    )
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
        assert risposta.status_code == 401
        assert signal.getsignal(signal.SIGTERM) is prima
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_porta_occupata_non_solleva() -> None:
    with socket.socket() as occupata:
        occupata.bind(("127.0.0.1", 0))
        occupata.listen()
        c = IotCittadiniSettings(http_porta=int(occupata.getsockname()[1]))
        await asyncio.wait_for(servi(_gestisci, c, adesso=lambda: datetime.now(UTC)), 5)
