"""Unit tests for the ITALICA event-catalogue parser (pure, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from shapely.geometry import box

from limen.cli import ingest_events
from limen.cli.ingest_events import _f, _parse_rows, _parse_utc
from limen.integrations.copernicus_ems.client import (
    ActivationTruth,
    ObservationMask,
    ObservedFlood,
)

_HEADER = (
    "id;information_source;landslide_type;lon;lat;municipality;province;region;"
    "geographic_accuracy;land_cover;elevation;slope;day;month;year;local_time;"
    "local_date;utc_date;temporal_accuracy;lon_raingauge;lat_raingauge;duration;"
    "cumulated_rainfall;;;;;;;"
)


def test_parse_utc_with_and_without_time() -> None:
    assert _parse_utc("12/11/2004 23:01") == datetime(2004, 11, 12, 23, 1, tzinfo=UTC)
    assert _parse_utc("07/03/2009") == datetime(2009, 3, 7, 0, 0, tzinfo=UTC)
    assert _parse_utc("") is None
    assert _parse_utc("not-a-date") is None


def test_f_handles_blanks_and_bad_values() -> None:
    assert _f("12.7") == 12.7
    assert _f("") is None
    assert _f(None) is None
    assert _f("n/a") is None


def test_parse_rows_maps_fields_and_skips_incomplete(tmp_path: Path) -> None:
    good = (
        "ITA_0001;IR;RF;16.173;40.592109;Calciano;Matera;Basilicata;P0;2.1.1;"
        "439;12.7;13;11;2004;00:01;13/11/2004 00:01;12/11/2004 23:01;T1;"
        "16.275;40.6347;33;49.8;;;;;;;"
    )
    # missing lon → skipped
    bad = "ITA_0002;NR;SL;;42.51;X;Y;Abruzzo;P1;2.4.3;427;10.2;19;5;2002;;;;;;;;;;;;;;;"
    csv_path = tmp_path / "italica.csv"
    csv_path.write_text("\n".join([_HEADER, good, bad]) + "\n", encoding="utf-8")

    events = _parse_rows(csv_path)

    assert len(events) == 1
    e = events[0]
    assert e.id == "ITA_0001"
    assert e.source == "IR"
    assert e.landslide_type == "RF"
    assert e.region == "Basilicata"
    assert e.event_time == datetime(2004, 11, 12, 23, 1, tzinfo=UTC)
    assert e.slope_deg == 12.7
    assert e.cumulated_rainfall_mm == 49.8
    assert (e.geom.x, e.geom.y) == (16.173, 40.592109)


# --- Copernicus EMS: il sync condiviso dal comando e dal passo notturno ------

_T = datetime(2024, 9, 19, tzinfo=UTC)


def _flood(i: int, geom: Any = None) -> ObservedFlood:
    return ObservedFlood(
        id=f"EMSR762-aoi01-DEL1-{i}-0",
        activation_code="EMSR762",
        aoi_label="AOI01",
        event_time=_T,
        observed_time=_T,
        geom=geom if geom is not None else box(11.8 + i, 44.2, 11.9 + i, 44.3),
        area_km2=1.0,
    )


_MASK = ObservationMask(
    id="EMSR762-aoi01-DEL1",
    activation_code="EMSR762",
    aoi_label="AOI01",
    product_type="DEL",
    observed_time=_T,
    geom=box(11.5, 44.0, 12.5, 44.5),
)


class _Db:
    """I repo sostituiti: registra le scritture invece di farle."""

    def __init__(self, *, versioni: set[str] | None = None) -> None:
        self.versioni = versioni or set()
        self.scritti: list[str] = []
        self.registrate: list[str] = []

    async def find(self, _src: str, _ds: str, version: str) -> object | None:
        return object() if version in self.versioni else None

    async def record(self, *, version: str, **_kw: object) -> int:
        self.registrate.append(version)
        return 1

    async def upsert_many(self, polygons: list[ObservedFlood]) -> int:
        self.scritti.append("poligoni")
        return len(polygons)

    async def upsert_masks(
        self, masks: list[ObservationMask], *, absent: list[str]
    ) -> tuple[int, int]:
        self.scritti.append("maschere")
        return len(masks), 0

    async def count_events(self) -> int:
        return 2


@pytest.fixture()
def db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Db:
    finto = _Db()
    monkeypatch.setenv("LIMEN_FLOOD_EVENTS_CACHE", str(tmp_path))

    async def attivazioni(**_kw: object) -> list[object]:
        return [SimpleNamespace(code="EMSR762", event_time=_T)]

    async def verita(_a: object, *, cache_dir: Path) -> ActivationTruth:
        return ActivationTruth(floods=[_flood(0), _flood(1)], masks=[_MASK])

    monkeypatch.setattr(ingest_events, "fetch_activations", attivazioni)
    monkeypatch.setattr(ingest_events, "fetch_activation_truth", verita)
    for nome in ("find", "record"):
        monkeypatch.setattr(ingest_events.dataset_versions_repo, nome, getattr(finto, nome))
    for nome in ("upsert_many", "upsert_masks", "count_events"):
        monkeypatch.setattr(ingest_events.flood_events_repo, nome, getattr(finto, nome))
    return finto


@pytest.mark.asyncio
async def test_un_catalogo_nuovo_si_scrive_e_si_registra(db: _Db) -> None:
    out = await ingest_events.sincronizza_alluvioni()
    assert out["esito"] == "scritto"
    assert db.scritti == ["poligoni", "maschere"]
    assert len(db.registrate) == 1


@pytest.mark.asyncio
async def test_lo_stesso_catalogo_non_riscrive_niente(db: _Db) -> None:
    await ingest_events.sincronizza_alluvioni()
    db.versioni = set(db.registrate)
    db.scritti.clear()
    out = await ingest_events.sincronizza_alluvioni()
    assert out["esito"] == "invariato"
    assert db.scritti == []


@pytest.mark.asyncio
async def test_senza_attivazioni_non_si_registra_una_versione(
    db: _Db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nessuna(**_kw: object) -> list[object]:
        return []

    monkeypatch.setattr(ingest_events, "fetch_activations", nessuna)
    out = await ingest_events.sincronizza_alluvioni()
    assert out["esito"] == "nessuna_attivazione"
    assert db.scritti == [] and db.registrate == []


def test_la_versione_non_dipende_dall_ordine_ma_dalla_geometria() -> None:
    a, b = _flood(0), _flood(1)
    assert ingest_events._versione([a, b], [_MASK], []) == ingest_events._versione(
        [b, a], [_MASK], []
    )
    spostato = _flood(0, geom=box(0, 0, 1, 1))
    assert ingest_events._versione([a, b], [_MASK], []) != ingest_events._versione(
        [spostato, b], [_MASK], []
    )
    assert ingest_events._versione([a, b], [_MASK], []) != ingest_events._versione(
        [a, b], [_MASK], ["EMSR762-aoi02-DEL1"]
    )
