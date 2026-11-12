"""Pluviometri ARPA Lombardia → pioggia oraria per nodo (#505)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from limen.integrations.arpa_lombardia import pluviometri as pl
from limen.integrations.arpa_lombardia.pluviometri import (
    Pluviometro,
    associa,
    dataset_per,
    ore_dai_dieci_minuti,
)


def _p(idsensore: str, lon: float, lat: float) -> Pluviometro:
    return Pluviometro(idsensore=idsensore, nome=idsensore, lon=lon, lat=lat, dal=None, al=None)


def test_dataset_per_periodo() -> None:
    assert dataset_per(datetime(2023, 5, 1, tzinfo=UTC), datetime(2023, 6, 1, tzinfo=UTC)) == [
        "pstb-pga6"
    ]
    assert dataset_per(datetime(2020, 12, 1, tzinfo=UTC), datetime(2021, 1, 31, tzinfo=UTC)) == [
        "2kar-pnuk",
        "pstb-pga6",
    ]
    assert dataset_per(datetime(2002, 11, 1, tzinfo=UTC), datetime(2002, 12, 1, tzinfo=UTC)) == [
        "e7r2-7m84"
    ]


def test_associa_il_piu_vicino_entro_il_raggio() -> None:
    vicino, lontano = _p("1", 9.00, 45.00), _p("2", 9.03, 45.00)
    nodi = [(9.01, 45.0), (10.0, 45.0)]
    assert associa(nodi, [vicino, lontano], raggio_km=5.0) == [vicino, None]
    assert associa(nodi, [], raggio_km=5.0) == [None, None]


def test_ore_in_utc_dall_ora_solare_e_giorni_non_misurati() -> None:
    start = datetime(2023, 5, 15, 0, tzinfo=UTC)
    end = datetime(2023, 5, 15, 3, tzinfo=UTC)
    # Etichette CET: l'ora UTC (01, 02] è (02:00, 03:00] in CET.
    pioggia = [
        ("A", "2023-05-15T02:10:00.000", 1.0),
        ("A", "2023-05-15T03:00:00.000", 0.5),
        ("A", "2023-05-15T03:10:00.000", 2.0),
        ("B", "2023-05-15T02:10:00.000", 9.0),
    ]
    # Finestra di tre ore: 18 misure attese; A le ha, B no.
    conteggi = [("A", date(2023, 5, 15), 18), ("B", date(2023, 5, 15), 3)]
    ore = ore_dai_dieci_minuti(pioggia, conteggi, sensori=["A", "B"], start=start, end=end)
    assert list(ore) == [
        datetime(2023, 5, 15, 1, tzinfo=UTC),
        datetime(2023, 5, 15, 2, tzinfo=UTC),
        datetime(2023, 5, 15, 3, tzinfo=UTC),
    ]
    assert ore[datetime(2023, 5, 15, 1, tzinfo=UTC)] == [0.0, None]
    assert ore[datetime(2023, 5, 15, 2, tzinfo=UTC)] == [1.5, None]
    assert ore[datetime(2023, 5, 15, 3, tzinfo=UTC)] == [2.0, None]


async def test_oraria_per_nodo_e_degrado(monkeypatch: pytest.MonkeyPatch) -> None:
    anagrafica = [
        {"idsensore": "A", "nomestazione": "a", "lng": "9.0", "lat": "45.0"},
        {"idsensore": "Z", "nomestazione": "z", "lng": "12.0", "lat": "45.0"},
    ]

    async def pagine(dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if dataset == pl.ANAGRAFICA:
            return anagrafica
        if "$group" in params:
            assert "idsensore in ('A')" in params["$where"]
            return [{"idsensore": "A", "giorno": "2023-05-15T00:00:00.000", "n": "18"}]
        return [{"idsensore": "A", "data": "2023-05-15T02:10:00.000", "valore": "4.2"}]

    monkeypatch.setattr(pl, "_pagine", pagine)
    start = datetime(2023, 5, 15, 0, tzinfo=UTC)
    end = datetime(2023, 5, 15, 3, tzinfo=UTC)
    nodi = [(9.01, 45.0), (10.0, 45.0)]
    ore = await pl.oraria(nodi, start, end, raggio_km=5.0, bbox=(8.0, 44.0, 11.0, 47.0))
    assert ore[datetime(2023, 5, 15, 2, tzinfo=UTC)] == [4.2, None]
    assert ore[datetime(2023, 5, 15, 3, tzinfo=UTC)] == [0.0, None]

    async def giu(dataset: str, params: dict[str, str]) -> list[dict[str, Any]]:
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(pl, "_pagine", giu)
    assert await pl.oraria(nodi, start, end, raggio_km=5.0, bbox=(8.0, 44.0, 11.0, 47.0)) == {}
