"""Il file del fact check: cosa entra nel registro e cosa viene rifiutato."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from shapely.geometry import Point

from limen.cli.registra_verifica import SORGENTE_STAMPA, frana_da_verifica, leggi
from limen.core.models.hazard import HazardType


def _registro(**evento: Any) -> dict[str, Any]:
    return {
        "slug": "2026-10-10-frana-san-lorenzo",
        "pericolo": "landslide",
        "esito": "mancata",
        "motivo": "sfondo Moderato, mai Alto",
        "evento": {
            "quando": "2026-10-10T12:00:00+02:00",
            "precisione_ora": "T3",
            "luogo": "San Lorenzo Marina (RC)",
            "regione": "Calabria",
            "comuni": ["080073"],
            **evento,
        },
        "fonti": [{"testata": "DIRE", "url": "https://www.dire.it/x"}],
        "misura": {"anticipo_ore_moderato": 80, "anticipo_ore_alto": None},
    }


def _scrivi(tmp_path: Path, payload: dict[str, Any]) -> Path:
    p = tmp_path / "v.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_un_evento_al_comune_non_porta_punto(tmp_path: Path) -> None:
    v = leggi(_scrivi(tmp_path, _registro()))
    assert v.hazard is HazardType.LANDSLIDE
    assert v.evento_at == datetime(2026, 10, 10, 10, tzinfo=UTC)
    assert v.punto is None
    assert v.comuni == ("080073",)
    assert v.misura["anticipo_ore_moderato"] == 80


def test_un_punto_dalla_notizia_porta_la_sua_precisione(tmp_path: Path) -> None:
    v = leggi(_scrivi(tmp_path, _registro(lon=15.83, lat=37.92, precisione_luogo="P1")))
    assert v.punto == Point(15.83, 37.92)
    assert v.precisione_luogo == "P1"


@pytest.mark.parametrize(
    "evento",
    [
        {"quando": "2026-10-10T12:00:00"},
        {"lon": 15.83},
        {"lon": 15.83, "lat": 37.92},
        {"precisione_ora": "mattina"},
        {"comuni": []},
    ],
    ids=["senza-fuso", "lon-senza-lat", "punto-senza-precisione", "ora-fuori-scala", "zero-comuni"],
)
def test_rifiuta_un_evento_incompleto(tmp_path: Path, evento: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        leggi(_scrivi(tmp_path, _registro(**evento)))


def test_rifiuta_un_esito_che_non_e_un_esito(tmp_path: Path) -> None:
    payload = _registro()
    payload["esito"] = "scartata"
    with pytest.raises(ValidationError):
        leggi(_scrivi(tmp_path, payload))


def test_la_frana_entra_nel_truth_set_con_la_scala_di_italica(tmp_path: Path) -> None:
    v = leggi(_scrivi(tmp_path, _registro()))
    e = frana_da_verifica(v, Point(15.8, 37.9), "P10")
    assert e.id == "stampa:2026-10-10-frana-san-lorenzo"
    assert e.source == SORGENTE_STAMPA
    assert e.temporal_accuracy == "T3"
    assert e.geographic_accuracy == "P10"
    assert e.attributes is not None
    assert e.attributes["fonti"] == ["https://www.dire.it/x"]
