"""Unit tests for the ITALICA event-catalogue parser (pure, no DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from limen.cli.ingest_events import _f, _parse_rows, _parse_utc

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
