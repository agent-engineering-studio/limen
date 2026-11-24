"""Pluviometri Meteotrentino → pioggia oraria per nodo."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from limen.integrations.meteotrentino import pluviometri as pt
from limen.integrations.meteotrentino.pluviometri import (
    OraStazione,
    file_per,
    ore_dai_cinque_minuti,
    ore_del_file,
)

_CET = pt._CET
_OTT = (datetime(2025, 10, 1, tzinfo=_CET), datetime(2025, 11, 1, tzinfo=_CET))


def _parquet(righe: list[tuple[str, str, datetime, float, int]]) -> bytes:
    tabella = pa.table(
        {
            "station": [r[0] for r in righe],
            "code": [r[1] for r in righe],
            "time": pa.array([r[2] for r in righe], type=pa.timestamp("ms", tz="Etc/GMT-1")),
            "value": [r[3] for r in righe],
            "quality": pa.array([r[4] for r in righe], type=pa.int16()),
        }
    )
    buf = io.BytesIO()
    pq.write_table(tabella, buf)
    return buf.getvalue()


def test_file_scelti_dal_mese_non_dall_intervallo() -> None:
    manifest = {
        "bulk/year=2025/2025-12.parquet": {
            "year": 2025,
            "month": 12,
            "first": "2024-12-31T09:05:00+01:00",
            "last": "2025-12-31T23:55:00+01:00",
        },
        # Ripete solo il pomeriggio del 31/12/2025, che sta già in 2025-12.
        "bulk/year=2026/2026-12.parquet": {
            "year": 2026,
            "month": 12,
            "first": "2025-12-31T09:05:00+01:00",
            "last": "2025-12-31T23:55:00+01:00",
        },
        "bulk/year=2026/2026-01.parquet": {
            "year": 2026,
            "month": 1,
            "first": "2026-01-01T00:00:00+01:00",
            "last": "2026-01-31T23:55:00+01:00",
        },
    }
    start = datetime(2025, 12, 31, 12, tzinfo=UTC)
    end = datetime(2026, 1, 1, 6, tzinfo=UTC)
    assert file_per(manifest, start, end) == [
        (
            "bulk/year=2025/2025-12.parquet",
            datetime(2025, 12, 1, tzinfo=_CET),
            datetime(2026, 1, 1, tzinfo=_CET),
        ),
        (
            "bulk/year=2026/2026-01.parquet",
            datetime(2026, 1, 1, tzinfo=_CET),
            datetime(2026, 2, 1, tzinfo=_CET),
        ),
    ]


def test_ore_del_file_solo_pioggia_accettata_del_mese() -> None:
    t = datetime(2025, 10, 1, 0, 5, tzinfo=_CET)
    contenuto = _parquet(
        [
            ("T0009", "10.00", t, 1.2, 1),
            ("T0009", "10.00", t + timedelta(minutes=5), 0.4, 145),
            ("T0009", "10.00", t + timedelta(minutes=10), 9.9, 140),
            ("T0009", "10.70", t, 7.0, 5),
            ("T0009", "400.00", t, 12.0, 1),
            ("T0010", "10.00", t, 3.0, 1),
            # Il 30 settembre ripetuto nel file di ottobre: è del file di settembre.
            ("T0009", "10.00", t - timedelta(minutes=10), 5.0, 1),
        ]
    )
    assert ore_del_file(contenuto, ["T0009"], da=_OTT[0], a=_OTT[1]) == [
        OraStazione(
            stazione="T0009",
            ora=datetime(2025, 10, 1, 0, tzinfo=UTC),
            misure=2,
            mm=1.6,
            teletrasmesse=1,
        )
    ]


def _ora(s: str, ora: datetime, misure: int, mm: float) -> OraStazione:
    return OraStazione(stazione=s, ora=ora, misure=misure, mm=mm, teletrasmesse=0)


def test_ore_in_utc_ore_incomplete_e_giorni_non_misurati() -> None:
    start = datetime(2025, 10, 1, 0, tzinfo=UTC)
    end = datetime(2025, 10, 1, 4, tzinfo=UTC)
    h = [start + timedelta(hours=k) for k in range(1, 5)]
    ore = [
        _ora("A", h[0], 12, 1.0),
        # Due file per la stessa ora si sommano.
        _ora("A", h[1], 6, 0.25),
        _ora("A", h[1], 6, 0.25),
        # Il temporale con due misure scartate: il giorno resta sopra il 90 %, l'ora no.
        _ora("A", h[2], 10, 0.0),
        _ora("A", h[3], 12, 0.0),
        # B salva solo l'intervallo piovoso, come prima del 2009.
        _ora("B", h[1], 12, 9.0),
    ]
    out = ore_dai_cinque_minuti(ore, sensori=["A", "B"], start=start, end=end)
    assert list(out) == h
    assert out[h[0]] == [1.0, None]
    assert out[h[1]] == [0.5, None]
    assert out[h[2]] == [None, None]
    assert out[h[3]] == [0.0, None]


async def test_oraria_per_nodo_e_degrado(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2025, 10, 1, 0, tzinfo=UTC)
    end = datetime(2025, 10, 1, 3, tzinfo=UTC)
    stazioni = {
        "features": [
            {
                "geometry": {"coordinates": [11.0, 46.0]},
                "properties": {
                    "code": "A",
                    "name": "a",
                    "first": "1990-01-01T00:00:00+01:00",
                    "last": "2026-11-24T03:55:00+01:00",
                    "codes": ["10.00", "400.00"],
                },
            },
            {
                # Solo temperatura: non è un pluviometro.
                "geometry": {"coordinates": [11.0, 46.0]},
                "properties": {
                    "code": "T",
                    "name": "t",
                    "first": "1990-01-01T00:00:00+01:00",
                    "last": "2026-11-24T03:55:00+01:00",
                    "codes": ["400.00"],
                },
            },
        ]
    }
    manifest = {
        "files": {
            "bulk/year=2025/2025-10.parquet": {
                "year": 2025,
                "month": 10,
                "first": "2025-10-01T00:00:00+01:00",
                "last": "2025-10-31T23:55:00+01:00",
            }
        }
    }
    righe = [("A", "10.00", start + timedelta(minutes=5 * k), 0.0, 145) for k in range(1, 37)]
    righe[20] = ("A", "10.00", start + timedelta(minutes=105), 4.2, 145)
    contenuto = _parquet(righe)

    async def scarica(percorso: str) -> httpx.Response:
        richiesta = httpx.Request("GET", f"{pt.BASE}/{percorso}")
        if percorso == pt.STAZIONI:
            return httpx.Response(200, json=stazioni, request=richiesta)
        if percorso == pt.MANIFEST:
            return httpx.Response(200, json=manifest, request=richiesta)
        return httpx.Response(200, content=contenuto, request=richiesta)

    monkeypatch.setattr(pt, "_scarica", scarica)
    nodi = [(11.01, 46.0), (12.0, 46.0)]
    bbox = (10.0, 45.0, 12.5, 47.0)
    ore = await pt.oraria(nodi, start, end, raggio_km=5.0, bbox=bbox)
    assert ore[start + timedelta(hours=2)] == [4.2, None]
    assert ore[start + timedelta(hours=3)] == [0.0, None]

    async def giu(percorso: str) -> Any:
        if percorso == pt.STAZIONI:
            return await scarica(percorso)
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(pt, "_scarica", giu)
    assert await pt.oraria(nodi, start, end, raggio_km=5.0, bbox=bbox) == {}

    async def anagrafica_giu(percorso: str) -> Any:
        raise httpx.ConnectError("giù")

    monkeypatch.setattr(pt, "_scarica", anagrafica_giu)
    assert await pt.pluviometri(bbox) == []
    assert await pt.oraria(nodi, start, end, raggio_km=5.0, bbox=bbox) == {}
