"""Il formato degli eventi degli enti (#509): cosa entra e cosa viene rifiutato."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import Point

from limen.cli.importa_eventi import (
    FormatoNonValidoError,
    leggi_file,
    slug,
    verifica_da_riga,
)
from limen.cli.registra_verifica import frana_da_verifica
from limen.core.models.hazard import HazardType

ESEMPIO = Path(__file__).parents[2] / "docs" / "guida" / "eventi-ente-esempio.csv"
_MISURA_VECCHIA: dict[str, Any] = {
    "evento": "2025-11-14T12:00:00+01:00",
    "storico_dal": "2026-10-01T00:00:00+00:00",
}


def _csv(tmp_path: Path, testo: str) -> Path:
    p = tmp_path / "eventi.csv"
    p.write_text(testo, encoding="utf-8")
    return p


def test_il_file_di_esempio_della_guida_si_legge() -> None:
    righe = leggi_file(ESEMPIO)
    assert [r.id for r in righe] == ["2025-017", "2025-018", "2025-021"]
    solo_giorno, con_ora, mezza = righe
    assert solo_giorno.pericolo is HazardType.LANDSLIDE
    assert solo_giorno.quando == (datetime(2025, 11, 14, 11, tzinfo=UTC), "T3")
    assert con_ora.quando[1] == "T1"
    assert (con_ora.lon, con_ora.lat, con_ora.precisione_luogo) == (15.8312, 38.0251, "P1")
    assert mezza.pericolo is HazardType.FLOOD
    assert mezza.quando[1] == "T2"


def test_virgola_codici_corti_e_nomi_inglesi(tmp_path: Path) -> None:
    p = _csv(
        tmp_path,
        "id,pericolo,data,comuni,luogo,fonte\n"
        'a1,wildfire,2026-08-02,"80005; 80063",Aspromonte,Regione Calabria\n',
    )
    (r,) = leggi_file(p)
    assert r.pericolo is HazardType.WILDFIRE
    assert r.comuni == ["080005", "080063"]


def test_geojson_di_punti(tmp_path: Path) -> None:
    p = tmp_path / "eventi.geojson"
    p.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [15.83, 38.02]},
                        "properties": {
                            "id": "7",
                            "pericolo": "frana",
                            "data": "2025-11-14",
                            "comuni": ["080005"],
                            "luogo": "Bagaladi",
                            "precisione_luogo": "P1",
                            "fonte": "Comune di Bagaladi",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (r,) = leggi_file(p)
    assert (r.lon, r.lat) == (15.83, 38.02)


@pytest.mark.parametrize(
    ("riga", "atteso"),
    [
        ("x1;terremoto;2025-11-14;;;080005;Bagaladi;;;;;;ente;", "pericolo"),
        ("x1;frana;14/11/2025;;;080005;Bagaladi;;;;;;ente;", "data"),
        ("x1;frana;2025-11-14;;;Bagaladi;Bagaladi;;;;;;ente;", "comuni"),
        ("x1;frana;2025-11-14;;;080005;Bagaladi;;15.8;;;;ente;", "lon e lat"),
        ("x1;frana;2025-11-14;;;080005;Bagaladi;;15.8;38.0;;;ente;", "precisione_luogo"),
        ("x1;frana;2025-11-14;;T1;080005;Bagaladi;;;;;;ente;", "T1 vuole l'ora"),
        ("x1;frana;2025-11-14;;;080005;Bagaladi;;;;;;;", "fonte"),
    ],
)
def test_una_riga_sbagliata_ferma_il_file(tmp_path: Path, riga: str, atteso: str) -> None:
    intestazione = ESEMPIO.read_text(encoding="utf-8").splitlines()[0]
    with pytest.raises(FormatoNonValidoError) as exc:
        leggi_file(_csv(tmp_path, f"{intestazione}\n{riga}\n"))
    assert any(atteso in e for e in exc.value.errori)
    assert all(e.startswith("riga 2") for e in exc.value.errori)


def test_una_colonna_sconosciuta_non_passa_in_silenzio(tmp_path: Path) -> None:
    p = _csv(
        tmp_path,
        "id;pericolo;data;comuni;luogo;fonte;precisone\nx;frana;2025-11-14;080005;B;e;P1\n",
    )
    with pytest.raises(FormatoNonValidoError, match="precisone"):
        leggi_file(p)


def test_id_ripetuto_e_poligono(tmp_path: Path) -> None:
    p = _csv(
        tmp_path,
        "id;pericolo;data;comuni;luogo;fonte\nx;frana;2025-11-14;080005;B;e\nx;frana;2025-11-15;080005;B;e\n",
    )
    with pytest.raises(FormatoNonValidoError, match="id ripetuto: x"):
        leggi_file(p)
    g = tmp_path / "p.geojson"
    g.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": []},
                        "properties": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(FormatoNonValidoError, match="serve un Point"):
        leggi_file(g)


def test_la_riga_diventa_una_verifica_con_ente_e_licenza() -> None:
    _, con_ora, _ = leggi_file(ESEMPIO)
    v = verifica_da_riga(
        con_ora, ente="Comune di Bagaladi", licenza="CC BY 4.0", misura=_MISURA_VECCHIA
    )
    assert v.slug == "2025-11-14-frana-ente-comune-di-bagaladi-2025-018"
    assert v.slug == slug(con_ora, "Comune di Bagaladi")
    assert v.esito == "non_verificabile"
    assert v.punto == Point(15.8312, 38.0251)
    assert v.fonti == (
        {
            "ente": "Comune di Bagaladi",
            "licenza": "CC BY 4.0",
            "id": "2025-018",
            "fonte": "Ufficio tecnico comunale, verbale 113/2025",
            "tipo": "scivolamento",
        },
    )
    frana = frana_da_verifica(v, v.punto, "P1", sorgente="ente")
    assert frana.source == "ente"
    assert frana.id == f"ente:{v.slug}"


def test_una_fonte_web_porta_il_suo_url() -> None:
    *_, mezza = leggi_file(ESEMPIO)
    v = verifica_da_riga(mezza, ente="Comune", licenza="CC BY 4.0", misura=_MISURA_VECCHIA)
    assert v.fonti[0]["url"] == "https://www.esempio.it/comunicato-22-11"
