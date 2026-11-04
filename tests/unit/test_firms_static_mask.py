"""The static-source mask labels NRT rows, which carry no FIRMS ``type``."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import firms_client as firms
import pytest

from limen.integrations.firms import archive, static_mask
from limen.integrations.firms.client import parse_hotspot_csv
from limen.integrations.firms.static_mask import load_static_mask

_ARCHIVE_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight,type"
)
_NRT_HEADER = (
    "country_id,latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,instrument,confidence,version,bright_ti5,frp,daynight"
)
_ILVA = (40.508, 17.210)
_WOODS = (40.5, 16.1)
_TODAY = date(2026, 11, 4)


def _archive_csv(year: int) -> str:
    rows = [
        f"{lat},{lon},330.1,0.5,0.5,{year}-08-0{day},1130,N,VIIRS,h,2,290.0,12.5,D,{kind}"
        for (lat, lon), kind in ((_ILVA, 2), (_WOODS, 0))
        for day in (1, 2, 3)
    ]
    return "\n".join([_ARCHIVE_HEADER, *rows]) + "\n"


def _nrt_csv() -> str:
    rows = [
        f"ITA,{lat},{lon},330.1,0.5,0.5,2026-11-04,1130,N,VIIRS,h,2.0NRT,290.0,12.5,D"
        for lat, lon in (_ILVA, _WOODS)
    ]
    return "\n".join([_NRT_HEADER, *rows]) + "\n"


def _mask() -> firms.StaticMask:
    return firms.build_static_mask(firms.parse_csv(_archive_csv(2024)))


def test_without_mask_nrt_rows_have_no_type() -> None:
    rows = parse_hotspot_csv(_nrt_csv(), source="VIIRS_SNPP_NRT")
    assert [h.detection_type for h in rows] == [None, None]


def test_mask_labels_the_steelworks_and_leaves_the_woods_alone() -> None:
    rows = parse_hotspot_csv(_nrt_csv(), source="VIIRS_SNPP_NRT", static_mask=_mask())
    by_place = {(h.latitude, h.longitude): h.detection_type for h in rows}
    assert by_place == {_ILVA: firms.STATIC_LAND_SOURCE, _WOODS: None}


def test_mask_never_overwrites_an_archive_type() -> None:
    rows = parse_hotspot_csv(_archive_csv(2024), source="VIIRS_SNPP_SP", static_mask=_mask())
    assert {h.detection_type for h in rows if (h.latitude, h.longitude) == _WOODS} == {0}


def _cache_every_year(root: Path, *, skip: set[int] = frozenset()) -> list[int]:
    years = archive.archive_years(static_mask._PRODUCT, until_year=_TODAY.year - 1)
    for year in years:
        if year in skip:
            continue
        path = archive._cache_path(product=static_mask._PRODUCT, year=year, country="Italy")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_archive_csv(year), encoding="utf-8")
    return years


async def _no_network(**_: object) -> None:
    return None


async def test_built_from_the_cached_archives_then_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))
    years = _cache_every_year(tmp_path)

    mask = await load_static_mask(today=_TODAY)
    assert mask is not None
    assert mask.meta["years"] == years
    saved = static_mask._mask_path(country="Italy", first=years[0], last=years[-1])
    assert saved.is_file()

    # Second call: from the file, with no archive read at all.
    monkeypatch.setattr(static_mask, "archive_text", _no_network)
    again = await load_static_mask(today=_TODAY)
    assert again is not None
    assert again.cells == mask.cells


async def test_a_missing_middle_year_is_used_but_not_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))
    years = _cache_every_year(tmp_path, skip={2018})
    real = archive.archive_text

    async def offline(
        *, product: archive.ArchiveProduct, year: int, country: str = "Italy"
    ) -> str | None:
        # A year not in the cache is a network failure here, never a download.
        return None if year == 2018 else await real(product=product, year=year, country=country)

    monkeypatch.setattr(static_mask, "archive_text", offline)
    mask = await load_static_mask(today=_TODAY)
    assert mask is not None
    assert 2018 not in mask.meta["years"]
    assert not static_mask._mask_path(country="Italy", first=years[0], last=years[-1]).exists()


async def test_no_archive_at_all_degrades_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(static_mask, "archive_text", _no_network)
    assert await load_static_mask(today=_TODAY) is None
