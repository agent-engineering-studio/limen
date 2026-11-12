"""FraneItalia → landslide_events: lettura, ore, precisione, doppioni (#500)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

from limen.cli.ingest_franeitalia import istante, leggi, togli_doppioni

_COLONNE = (
    "ID",
    "Class",
    "Number",
    "Magnitude category",
    "LAT",
    "LONG",
    "Region",
    "Municipality(-ies)",
    "Site(s)",
    "Sd",
    "Initial day",
    "Time",
    "Final day",
    "Td",
    "Typology",
    "Trigger",
)


def _gpkg(tmp_path: Path, righe: list[tuple[object, ...]]) -> Path:
    path = tmp_path / "fi.gpkg"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
    con.execute("INSERT INTO gpkg_contents VALUES ('frane', 'features')")
    con.execute("CREATE TABLE frane (" + ", ".join(f'"{c}"' for c in _COLONNE) + ")")
    con.executemany(f"INSERT INTO frane VALUES ({', '.join('?' * len(_COLONNE))})", righe)
    con.commit()
    con.close()
    return path


def _riga(id_: int, **campi: object) -> tuple[object, ...]:
    base: dict[str, object] = {
        "ID": id_,
        "Class": "C3",
        "Number": 1,
        "Magnitude category": "SLE",
        "LAT": 40.0,
        "LONG": 16.0,
        "Region": "Basilicata",
        "Municipality(-ies)": "Pisticci",
        "Site(s)": None,
        "Sd": "A",
        "Initial day": "15/03/23",
        "Time": None,
        "Final day": None,
        "Td": "certain",
        "Typology": None,
        "Trigger": "rainfall",
    }
    base.update(campi)
    return tuple(base[c] for c in _COLONNE)


def test_ora_esatta_parte_del_giorno_e_giorno_solo() -> None:
    giorno = date(2023, 7, 15)
    assert istante(giorno, "17:30", True) == (datetime(2023, 7, 15, 15, 30, tzinfo=UTC), "T1")
    assert istante(giorno, "morning", True) == (datetime(2023, 7, 15, 7, 0, tzinfo=UTC), "T2")
    assert istante(giorno, None, True) == (datetime(2023, 7, 15, 10, 0, tzinfo=UTC), "T3")
    # Inverno: +01. Una data stimata non tiene l'ora, anche se c'è.
    assert istante(date(2023, 1, 5), "17:30", False) == (
        datetime(2023, 1, 5, 11, 0, tzinfo=UTC),
        "T3",
    )


def test_leggi_mappa_precisione_e_toglie_le_cause_non_meteo(tmp_path: Path) -> None:
    path = _gpkg(
        tmp_path,
        [
            _riga(1, Sd="A", Time="9:00"),
            _riga(2, Sd="M"),
            _riga(3, Sd="AE", **{"Magnitude category": "ALE", "Number": 12}),
            _riga(4, Trigger="earthquake"),
            _riga(5, Trigger="human activity"),
            _riga(6, Trigger="n.a.", Td="estimation"),
            _riga(7, **{"Initial day": None}),
        ],
    )
    eventi, altre_cause, illeggibili = leggi(path)
    assert (altre_cause, illeggibili) == (2, 1)
    per_id = {e.id: e for e in eventi}
    assert set(per_id) == {"franeitalia:1", "franeitalia:2", "franeitalia:3", "franeitalia:6"}
    assert per_id["franeitalia:1"].geographic_accuracy == "P1"
    assert per_id["franeitalia:1"].temporal_accuracy == "T1"
    assert per_id["franeitalia:2"].geographic_accuracy == "P10"
    assert per_id["franeitalia:3"].geographic_accuracy == "P100"
    assert per_id["franeitalia:3"].attributes is not None
    assert per_id["franeitalia:3"].attributes["numero_frane"] == 12
    assert per_id["franeitalia:6"].attributes is not None
    assert per_id["franeitalia:6"].attributes["data_stimata"] is True
    assert all(e.source == "franeitalia" for e in eventi)


def test_doppioni_di_italica_entro_cinque_km_e_un_giorno(tmp_path: Path) -> None:
    path = _gpkg(
        tmp_path,
        [
            _riga(1, **{"Initial day": "10/11/19"}),
            _riga(2, **{"Initial day": "10/11/19"}, LONG=16.2),
            _riga(3, **{"Initial day": "14/11/19"}),
        ],
    )
    eventi, _, _ = leggi(path)
    italica = [(datetime(2019, 11, 9, 22, 0, tzinfo=UTC), 16.01, 40.01)]
    tenuti, doppioni = togli_doppioni(eventi, italica)
    assert doppioni == 1
    assert {e.id for e in tenuti} == {"franeitalia:2", "franeitalia:3"}
