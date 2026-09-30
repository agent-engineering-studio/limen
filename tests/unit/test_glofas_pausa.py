"""GloFAS in pausa dopo il limite giornaliero (#149).

Il 429 di Open-Meteo dice «Daily API request limit exceeded. Please try again
tomorrow». La politica di retry condivisa lo tratta come un 429 qualunque —
quattro tentativi, attesa fino a 60 s — e lo faceva per ogni blocco di cento
nodi: il 30 settembre la previsione d'alluvione è rimasta mezz'ora sui
tentativi della prima regione, 88 volte 429, senza scrivere una riga.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from limen.integrations.openmeteo import flood as fl


@pytest.fixture(autouse=True)
def _senza_pausa(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Stato di modulo: ogni test parte pulito, e la cache non c'è.
    monkeypatch.setattr(fl, "_pausa_fino", None)
    monkeypatch.setattr(fl, "_ultimo_controllo", None)

    class _Cache:
        async def get_json(self, _key: str) -> Any:
            return None

        async def set_json(self, _key: str, _value: Any, *, ttl_seconds: int) -> None:
            return None

    monkeypatch.setattr("limen.data.caching.postgres_cache.PostgresCache", _Cache)
    yield


def _risposta_429() -> httpx.HTTPStatusError:
    req = httpx.Request("GET", fl.FLOOD_URL)
    resp = httpx.Response(429, request=req, json={"reason": "Daily API request limit exceeded"})
    return httpx.HTTPStatusError("429", request=req, response=resp)


def _nodi(n: int) -> list[tuple[float, float]]:
    return [(12.0 + i * 0.1, 44.0) for i in range(n)]


@pytest.mark.asyncio
async def test_dopo_il_primo_429_non_si_richiama_glofas(monkeypatch: pytest.MonkeyPatch) -> None:
    chiamate: list[str] = []

    async def _fetch(_method: str, url: str, **_kw: Any) -> httpx.Response:
        chiamate.append(url)
        raise _risposta_429()

    monkeypatch.setattr(fl, "fetch_with_retry", _fetch)
    client = fl.OpenMeteoFloodClient()

    # Tre blocchi da cento: senza pausa sarebbero tre raffiche di tentativi.
    punti = await client.fetch_grid(fl.FLOOD_URL, _nodi(250), {}, "openmeteo.flood.fluvial_grid")

    assert chiamate == [fl.FLOOD_URL]
    # Allineato ai nodi: chi chiama mappa per posizione.
    assert len(punti) == 250
    assert all(p == {} for p in punti)


@pytest.mark.asyncio
async def test_la_pausa_dura_fino_alla_mezzanotte_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fetch(_method: str, _url: str, **_kw: Any) -> httpx.Response:
        raise _risposta_429()

    monkeypatch.setattr(fl, "fetch_with_retry", _fetch)
    await fl.OpenMeteoFloodClient()._get(fl.FLOOD_URL, {}, "openmeteo.flood.fluvial")

    assert fl._pausa_fino is not None
    assert fl._pausa_fino > datetime.now(UTC)
    assert (fl._pausa_fino.hour, fl._pausa_fino.minute) == (0, 0)


@pytest.mark.asyncio
async def test_la_pausa_non_tocca_la_pioggia(monkeypatch: pytest.MonkeyPatch) -> None:
    """Solo GloFAS: la pioggia viene dalla nostra istanza, e il ramo
    pluviale è quello su cui l'alluvione si misura mentre GloFAS tace."""
    monkeypatch.setattr(fl, "_pausa_fino", datetime(2999, 1, 1, tzinfo=UTC))
    chiamate: list[str] = []

    async def _fetch(_method: str, url: str, **_kw: Any) -> httpx.Response:
        chiamate.append(url)
        return httpx.Response(200, json={"hourly": {"precipitation": [1.0]}})

    monkeypatch.setattr(fl, "fetch_with_retry", _fetch)
    await fl.OpenMeteoFloodClient()._get(fl.FORECAST_URL, {}, "openmeteo.flood.pluvial")

    assert chiamate == [fl.FORECAST_URL]


@pytest.mark.asyncio
async def test_un_errore_che_non_e_429_non_mette_in_pausa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Un 503 passa: è il caso per cui il retry esiste.
    async def _fetch(_method: str, _url: str, **_kw: Any) -> httpx.Response:
        req = httpx.Request("GET", fl.FLOOD_URL)
        raise httpx.HTTPStatusError("503", request=req, response=httpx.Response(503, request=req))

    monkeypatch.setattr(fl, "fetch_with_retry", _fetch)
    await fl.OpenMeteoFloodClient()._get(fl.FLOOD_URL, {}, "openmeteo.flood.fluvial")

    assert fl._pausa_fino is None
