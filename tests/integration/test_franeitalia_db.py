"""FraneItalia in ``landslide_events`` contro un Postgres vero (#500)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from shapely.geometry import Point

from limen.cli.ingest_franeitalia import carica
from limen.data.db import acquire
from limen.data.repos.landslide_events_repo import LandslideEvent, upsert_many

pytestmark = pytest.mark.integration

_COLONNE = ("ID", "LAT", "LONG", "Sd", "Initial day", "Time", "Td", "Trigger")
_ALTRE = (
    "Class",
    "Number",
    "Magnitude category",
    "Region",
    "Municipality(-ies)",
    "Site(s)",
    "Final day",
    "Typology",
)


def _gpkg(tmp_path: Path) -> Path:
    path = tmp_path / "fi.gpkg"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE gpkg_contents (table_name TEXT, data_type TEXT)")
    con.execute("INSERT INTO gpkg_contents VALUES ('frane', 'features')")
    tutte = _COLONNE + _ALTRE
    con.execute("CREATE TABLE frane (" + ", ".join(f'"{c}"' for c in tutte) + ")")
    nomi = ", ".join(f'"{c}"' for c in _COLONNE)
    con.executemany(
        f"INSERT INTO frane ({nomi}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 40.0, 16.0, "A", "10/11/19", None, "certain", "rainfall"),
            (2, 40.0, 16.0, "C", "15/03/23", "morning", "certain", "rainfall"),
            (3, 40.0, 16.0, "A", "16/03/23", None, "certain", "earthquake"),
        ],
    )
    con.commit()
    con.close()
    return path


async def test_carica_toglie_i_doppioni_e_non_riscrive(
    reset_db: None, pg_pool: object, tmp_path: Path
) -> None:
    await upsert_many(
        [
            LandslideEvent(
                id="ITA_1",
                source="NR",
                event_time=datetime(2019, 11, 10, 8, 0, tzinfo=UTC),
                geom=Point(16.01, 40.01),
                attributes={"catalogue": "italica"},
            )
        ]
    )
    path = _gpkg(tmp_path)
    conti = await carica(path)
    assert conti is not None
    assert (conti.letti, conti.tenuti, conti.doppioni, conti.altre_cause) == (3, 1, 1, 1)
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT id, geographic_accuracy, temporal_accuracy, event_time "
            "FROM landslide_events WHERE source = 'franeitalia'"
        )
    assert [(r["id"], r["geographic_accuracy"], r["temporal_accuracy"]) for r in righe] == [
        ("franeitalia:2", "P10", "T2")
    ]
    assert righe[0]["event_time"] == datetime(2023, 3, 15, 8, 0, tzinfo=UTC)
    assert await carica(path) is None
