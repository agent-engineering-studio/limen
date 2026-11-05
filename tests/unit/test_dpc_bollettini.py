"""Il bollettino di criticità DPC (#155): le parti pure dell'import.

Il bollettino è già strutturato — testo del livello, zona, poligono — e
questi test fissano come lo legge ``dpc_radar.bulletins``, senza rete: è ciò
che finisce in ``dpc_allerte``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from dpc_radar.bulletins import issued as emissione
from dpc_radar.bulletins import level as livello
from dpc_radar.bulletins import zones_from_geojson as zone_da_geojson

from limen.integrations.dpc import bollettini

_NESSUNA = "Assenza di fenomeni significativi prevedibili / NESSUNA ALLERTA"


def test_il_livello_si_legge_dal_colore_scritto() -> None:
    assert livello("Assenza di fenomeni significativi prevedibili / NESSUNA ALLERTA") == 0
    assert livello("Ordinaria per rischio temporali / ALLERTA GIALLA") == 1
    assert livello("Moderata per rischio idrogeologico / ALLERTA ARANCIONE") == 2
    assert livello("Elevata per rischio idraulico / ALLERTA ROSSA") == 3
    assert livello(None) == 0


def test_l_emissione_viene_dal_nome_del_file_in_ora_italiana() -> None:
    e = emissione("20261005_1417_today.json")
    assert e is not None
    assert (e.date(), e.hour, e.minute) == (date(2026, 10, 5), 14, 17)
    assert e.utcoffset() is not None
    assert emissione("20261005_1417_tomorrow.json") is None


def test_le_zone_portano_i_tre_rischi_e_un_multipoligono() -> None:
    dati = {
        "features": [
            {
                "properties": {
                    "Nome zona": "Bacino di Levante / Carso",
                    "Rappresentata nella mappa": "Ordinaria per rischio temporali / ALLERTA GIALLA",
                    "Per rischio idrogeologico": _NESSUNA,
                    "Per rischio idraulico": _NESSUNA,
                    "Per rischio temporali": "Ordinaria per rischio temporali / ALLERTA GIALLA",
                    "Comuni": ["Trieste"],
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[13.7, 45.6], [13.9, 45.6], [13.9, 45.7], [13.7, 45.6]]],
                },
            },
            # Una zona senza nome non entra: non si saprebbe a chi attribuirla.
            {"properties": {}, "geometry": {"type": "Point", "coordinates": [13.7, 45.6]}},
        ]
    }
    [zona] = zone_da_geojson(dati, date(2026, 10, 6))
    assert zona.name == "Bacino di Levante / Carso"
    assert (zona.level, zona.hydrogeological, zona.hydraulic, zona.thunderstorms) == (1, 0, 0, 1)
    assert zona.geometry.geom_type == "MultiPolygon"


_API = "https://api.github.com/repos/pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica"
_RAW = (
    "https://raw.githubusercontent.com/pcm-dpc/"
    "DPC-Bollettini-Criticita-Idrogeologica-Idraulica/master/files/geojson"
)


def _rete(monkeypatch: pytest.MonkeyPatch, risposte: dict[str, httpx.Response]) -> list[str]:
    viste: list[str] = []

    async def _fetch(method: str, url: str, **_kw: Any) -> httpx.Response:
        viste.append(url)
        risposta = risposte.get(url, httpx.Response(404))
        risposta.request = httpx.Request(method, url)
        return risposta

    monkeypatch.setattr(bollettini, "fetch_with_retry", _fetch)
    return viste


def _albero(*voci: dict[str, str]) -> httpx.Response:
    return httpx.Response(200, json={"tree": list(voci)})


async def test_l_ultimo_nome_passa_da_http(monkeypatch: pytest.MonkeyPatch) -> None:
    viste = _rete(
        monkeypatch,
        {
            f"{_API}/git/trees/master": _albero({"path": "files", "sha": "f"}),
            f"{_API}/git/trees/f": _albero({"path": "geojson", "sha": "g"}),
            f"{_API}/git/trees/g": _albero(
                {"path": "20261004_1400_today.json"}, {"path": "20261005_1417_today.json"}
            ),
        },
    )
    assert await bollettini.ultimo_nome() == "20261005_1417_today.json"
    assert len(viste) == 3


async def test_github_che_non_risponde_degrada_a_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _rete(monkeypatch, {f"{_API}/git/trees/master": httpx.Response(200, text="<html>")})
    assert await bollettini.ultimo_nome() is None
    assert await bollettini.scarica("20261005_1417_today.json") is None


async def test_scarica_legge_oggi_e_domani(monkeypatch: pytest.MonkeyPatch) -> None:
    zona = {
        "properties": {"Nome zona": "Carso", "Rappresentata nella mappa": "ALLERTA GIALLA"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[13.7, 45.6], [13.9, 45.6], [13.9, 45.7], [13.7, 45.6]]],
        },
    }
    corpo = {"features": [zona]}
    _rete(
        monkeypatch,
        {
            f"{_RAW}/20261005_1417_today.json": httpx.Response(200, json=corpo),
            f"{_RAW}/20261005_1417_tomorrow.json": httpx.Response(200, json=corpo),
        },
    )
    b = await bollettini.scarica("20261005_1417_today.json")
    assert b is not None
    assert b.name == "20261005_1417"
    assert [z.valid for z in b.zones] == [date(2026, 10, 5), date(2026, 10, 6)]
