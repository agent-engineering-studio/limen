"""CAP 1.2 (#499) e OGC API Features (#503): i documenti, senza database."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from limen.core.models.hazard import HazardType
from limen.core.standard import cap, ogc

_C = cap.ComuneInAllerta(
    istat_code="080063",
    name="Reggio di Calabria",
    hazard=HazardType.FLOOD,
    worst_class="High",
    max_score=0.734,
    n_cells=230,
    n_alert=12,
    computed_at=datetime(2026, 11, 9, 13, 5, 7, 123456, tzinfo=UTC),
)


def _testo(xml: bytes, percorso: str) -> str | None:
    ns = {"c": cap.NS}
    return ET.fromstring(xml).findtext(percorso, namespaces=ns)


def test_il_messaggio_non_si_presenta_mai_come_reale() -> None:
    xml = cap.messaggio(_C)
    assert _testo(xml, "c:status") == "Exercise"
    assert "non è un sistema di allertamento ufficiale" in (_testo(xml, "c:note") or "")
    cfg = cap.carica_config().model_dump()
    cfg["status"] = "Actual"
    with pytest.raises(ValidationError):
        cap.ConfigCap.model_validate(cfg)


def test_campi_dalla_classe_ora_di_roma_e_attribuzione() -> None:
    xml = cap.messaggio(_C)
    assert _testo(xml, "c:sent") == "2026-11-09T14:05:07+01:00"
    assert _testo(xml, "c:info/c:expires") == "2026-11-09T17:05:07+01:00"
    assert _testo(xml, "c:info/c:category") == "Met"
    assert _testo(xml, "c:info/c:severity") == "Moderate"
    desc = _testo(xml, "c:info/c:description") or ""
    assert "12 celle da 1 km² su 230" in desc
    assert "0.73" in desc
    assert "Copernicus Emergency Management Service, 2026" in desc
    frana = cap.messaggio(_frana())
    assert "Copernicus" not in (_testo(frana, "c:info/c:description") or "")


def _frana() -> cap.ComuneInAllerta:
    return replace(_C, hazard=HazardType.LANDSLIDE, worst_class="VeryHigh")


def test_identificativo_andata_e_ritorno() -> None:
    ident = cap.identificativo(_C)
    assert ident == "limen-flood-080063-20261109T140507"
    assert cap.da_identificativo(ident) == (HazardType.FLOOD, "080063", "20261109T140507")
    assert cap.da_identificativo("limen-terremoto-1-2") is None
    assert cap.da_identificativo("altro") is None


def test_feed_atom_un_entry_per_comune() -> None:
    feed = cap.feed_atom(
        [_C, _frana()], base_url="https://limen.example/", aggiornato=_C.computed_at
    )
    ns = {"a": "http://www.w3.org/2005/Atom"}
    radice = ET.fromstring(feed)
    links = [e.find("a:link", ns) for e in radice.findall("a:entry", ns)]
    assert [link.get("href") for link in links if link is not None] == [
        "https://limen.example/api/cap/limen-flood-080063-20261109T140507",
        "https://limen.example/api/cap/limen-landslide-080063-20261109T140507",
    ]


def test_ogc_parametri() -> None:
    f = ogc.filtro(bbox="10,40,12,42", datetime_="2026-11-01T00:00:00Z/..", limit=5000, offset=3)
    assert f.bbox == (10.0, 40.0, 12.0, 42.0)
    assert f.dal == datetime(2026, 11, 1, tzinfo=UTC)
    assert f.al is None
    assert f.limit == ogc.LIMITE_MASSIMO
    assert ogc.filtro(bbox=None, datetime_=None, limit=None, offset=None).limit == 10
    for kw in (
        {"bbox": "12,40,10,42"},
        {"bbox": "a,b,c,d"},
        {"datetime_": "ieri"},
        {"datetime_": "2026-11-01T00:00:00"},
        {"limit": 0},
        {"offset": -1},
    ):
        args: dict[str, Any] = {"bbox": None, "datetime_": None, "limit": None, "offset": None}
        args.update(kw)
        with pytest.raises(ogc.ParametroNonValidoError):
            ogc.filtro(**args)


def test_ogc_collezione_e_pagina() -> None:
    assert ogc.da_id_collezione("comuni-wildfire") is HazardType.WILDFIRE
    assert ogc.da_id_collezione("celle-wildfire") is None
    col = ogc.collezione("http://x/api/ogc", HazardType.FLOOD, anno=2026)
    assert "Copernicus" in col["attribution"]
    assert (
        "Copernicus"
        not in ogc.collezione("http://x/api/ogc", HazardType.WILDFIRE, anno=2026)["attribution"]
    )
    f = ogc.filtro(bbox=None, datetime_=None, limit=1, offset=0)
    riga = {"istat_code": "1", "computed_at": _C.computed_at, "geometry": None}
    p = ogc.pagina(
        [riga],
        totale=3,
        base="http://x/api/ogc",
        id_collezione_="comuni-flood",
        f=f,
        query="limit=1&bbox=1,2,3,4",
        adesso=_C.computed_at,
    )
    assert p["features"][0]["properties"]["computed_at"] == "2026-11-09T13:05:07.123456+00:00"
    nxt = next(link["href"] for link in p["links"] if link["rel"] == "next")
    assert nxt == "http://x/api/ogc/collections/comuni-flood/items?bbox=1,2,3,4&limit=1&offset=1"
