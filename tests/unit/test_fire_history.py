"""Archivio storico FIRMS: classificazione, scarico e `ingest-fire-history` (#66, #116).

Due cose che il codice può sbagliare in silenzio, entrambe provate qui perché
non richiedono rete:

1. **La classe della detection.** FIRMS pubblica una colonna `type` che dice
   *cosa* ha visto il satellite. Ignorarla ha prodotto una densità del fuoco
   la cui cella massima d'Italia era l'ILVA di Taranto, con 3.308
   giorni-incendio su ~4.700 giorni d'archivio. Il filtro di confidenza non
   la toglieva e non poteva: un'acciaieria è calda davvero.
2. **Il riconoscimento di un corpo che non è un CSV.** Gli anni non
   pubblicati non rispondono sempre 404, e un messaggio d'errore dato in
   pasto al parser produce zero righe senza spiegare perché.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

from limen.cli import ingest_fire_history as cli
from limen.data.repos.fire_repo import FireHotspot
from limen.integrations._http import SharedHttpClient
from limen.integrations.firms import archive
from limen.integrations.firms.archive import (
    ARCHIVE_PRODUCTS,
    ARCHIVE_URL,
    _looks_like_hotspot_csv,
    archive_years,
)
from limen.integrations.firms.client import parse_hotspot_csv

_VIIRS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight,type"
)


def _viirs_row(*, lat: float, lon: float, detection_type: int, confidence: str = "h") -> str:
    return (
        f"{lat},{lon},330.1,0.5,0.5,2024-08-01,1130,N,VIIRS,"
        f"{confidence},2,290.0,12.5,D,{detection_type}"
    )


def test_detection_type_is_parsed_from_the_archive_csv() -> None:
    payload = "\n".join(
        [
            _VIIRS_HEADER,
            _viirs_row(lat=40.5, lon=16.1, detection_type=0),
            _viirs_row(lat=40.508, lon=17.210, detection_type=2),
            _viirs_row(lat=37.75, lon=14.99, detection_type=1),
            _viirs_row(lat=40.0, lon=18.5, detection_type=3),
        ]
    )

    hotspots = parse_hotspot_csv(payload, source="VIIRS_SNPP_SP")

    assert [h.detection_type for h in hotspots] == [0, 2, 1, 3]


def test_a_steelworks_is_high_confidence_so_only_the_class_separates_it() -> None:
    """Il motivo per cui il filtro di qualità non bastava.

    La detection di Taranto ha confidenza alta e potenza radiativa alta: passa
    ogni soglia di qualità, perché è una misura corretta di un oggetto molto
    caldo. Solo `type` dice che non è un incendio.
    """
    payload = "\n".join(
        [
            _VIIRS_HEADER,
            _viirs_row(lat=40.508, lon=17.210, detection_type=2, confidence="h"),
        ]
    )

    hotspots = parse_hotspot_csv(
        payload, source="VIIRS_SNPP_SP", min_confidence="high", min_frp_mw=10.0
    )

    assert len(hotspots) == 1, "il filtro di qualità la tiene, ed è corretto"
    assert hotspots[0].detection_type == 2, "la classe è l'unica cosa che la esclude"


def test_missing_type_column_leaves_the_class_unknown() -> None:
    """Un feed che non porta la colonna non deve far inventare uno zero.

    `fire_events` conta solo il tipo 0, quindi `None` tiene la detection fuori
    dagli eventi: sbagliare per difetto perde qualche giorno, sbagliare per
    eccesso rimette un'acciaieria nel truth set ogni giorno.
    """
    header = _VIIRS_HEADER.replace(",type", "")
    row = _viirs_row(lat=40.5, lon=16.1, detection_type=0).rsplit(",", 1)[0]

    hotspots = parse_hotspot_csv("\n".join([header, row]), source="VIIRS_SNPP_SP")

    assert len(hotspots) == 1
    assert hotspots[0].detection_type is None


def test_an_error_body_is_not_mistaken_for_a_csv() -> None:
    assert _looks_like_hotspot_csv(_VIIRS_HEADER)
    assert not _looks_like_hotspot_csv('{"error":"not found"}')
    assert not _looks_like_hotspot_csv("")
    # Un HTML di errore contiene parole comuni ma non le colonne richieste.
    assert not _looks_like_hotspot_csv("<html><body>Not Found</body></html>")


def test_archive_url_matches_the_published_layout() -> None:
    url = ARCHIVE_URL.format(source="viirs-snpp", year=2020, country="Italy")
    assert url == (
        "https://firms.modaps.eosdis.nasa.gov/data/country/"
        "viirs-snpp/2020/viirs-snpp_2020_Italy.csv"
    )


def test_each_product_starts_at_its_own_first_published_year() -> None:
    """MODIS dal 2000, VIIRS dal 2012: chiedere a VIIRS il 2005 è una
    richiesta sprecata verso una risposta che non è un CSV."""
    by_slug = {p.slug: p for p in ARCHIVE_PRODUCTS}

    assert by_slug["modis"].first_year == 2000
    assert by_slug["viirs-snpp"].first_year == 2012
    assert archive_years(by_slug["viirs-snpp"], until_year=2014) == [2012, 2013, 2014]
    assert archive_years(by_slug["modis"], until_year=2001) == [2000, 2001]


def test_sources_are_distinct_from_the_nrt_products() -> None:
    """L'archivio è standard processing, l'NRT è un altro prodotto.

    La chiave naturale di `fire_hotspots` contiene `source`: schiacciarli sullo
    stesso valore renderebbe impossibile sapere da dove viene una detection, e
    un riprocessamento sovrascriverebbe una riga NRT con una d'archivio.
    """
    sources = {p.source for p in ARCHIVE_PRODUCTS}

    assert sources == {"MODIS_SP", "VIIRS_SNPP_SP"}
    assert not any(s.endswith("_NRT") for s in sources)


# ---------------------------------------------------------------------------
# Scarico e cache dell'archivio
# ---------------------------------------------------------------------------
_MODIS = next(p for p in ARCHIVE_PRODUCTS if p.slug == "modis")
_CSV = "\n".join(
    [
        _VIIRS_HEADER,
        _viirs_row(lat=40.5, lon=16.1, detection_type=0),
        _viirs_row(lat=40.6, lon=16.2, detection_type=0, confidence="l"),
    ]
)


@pytest.fixture(autouse=True)
async def _close_http():
    yield
    await SharedHttpClient.aclose()


@respx.mock
async def test_a_downloaded_year_is_cached_and_then_read_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))
    url = ARCHIVE_URL.format(source="modis", year=2021, country="Italy")
    route = respx.get(url).mock(return_value=httpx.Response(200, text=_CSV))

    first = await archive.fetch_archive_year(product=_MODIS, year=2021)
    second = await archive.fetch_archive_year(product=_MODIS, year=2021)

    # Confidenza "l" sotto il minimo nominale: fuori, come nel feed NRT.
    assert len(first) == len(second) == 1
    assert first[0].source == "MODIS_SP"
    assert route.call_count == 1
    assert (tmp_path / "fires" / "firms" / "modis_2021_Italy.csv").read_text() == _CSV


@respx.mock
async def test_an_unpublished_year_answering_200_is_not_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """211 byte di JSON con esito 200: niente cache, niente righe fantasma."""
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))
    respx.get(ARCHIVE_URL.format(source="modis", year=2030, country="Italy")).mock(
        return_value=httpx.Response(200, json={"error": "not available"})
    )
    respx.get(ARCHIVE_URL.format(source="modis", year=2031, country="Italy")).mock(
        return_value=httpx.Response(404)
    )
    assert await archive.fetch_archive_year(product=_MODIS, year=2030) == []
    assert await archive.fetch_archive_year(product=_MODIS, year=2031) == []
    assert not (tmp_path / "fires").exists()


async def test_an_unreachable_archive_degrades_to_an_empty_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_DATA_DIR", str(tmp_path))

    async def _down(*_a: Any, **_k: Any) -> Any:
        raise httpx.ConnectError("nasa giù")

    monkeypatch.setattr(archive, "fetch_with_retry", _down)
    assert await archive.fetch_archive_year(product=_MODIS, year=2021, use_cache=False) == []


# ---------------------------------------------------------------------------
# `limen ingest-fire-history`
# ---------------------------------------------------------------------------
def _hotspot(day: date, lat: float = 40.5, source: str = "MODIS_SP") -> FireHotspot:
    return FireHotspot(source=source, acq_date=day, acq_time=1130, latitude=lat, longitude=16.1)


def test_year_bounds_default_to_last_published_year(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIMEN_FIRE_HISTORY_FROM", raising=False)
    monkeypatch.delenv("LIMEN_FIRE_HISTORY_TO", raising=False)
    assert cli._year_bounds() == (0, datetime.now(UTC).year - 1)
    monkeypatch.setenv("LIMEN_FIRE_HISTORY_FROM", "2019")
    monkeypatch.setenv("LIMEN_FIRE_HISTORY_TO", "2020")
    assert cli._year_bounds() == (2019, 2020)


def test_hotspots_hash_ignores_download_order() -> None:
    a, b = _hotspot(date(2024, 8, 1)), _hotspot(date(2024, 8, 2), lat=40.7)
    assert cli._hotspots_hash([a, b]) == cli._hotspots_hash([b, a])
    assert cli._hotspots_hash([a]) != cli._hotspots_hash([a, b])


async def test_local_csv_takes_its_source_from_the_file_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    csv = tmp_path / "viirs-snpp_2020_Italy.csv"
    csv.write_text(_CSV, encoding="utf-8")

    monkeypatch.delenv("LIMEN_FIRMS_CSV", raising=False)
    assert await cli._from_local_csv() is None

    monkeypatch.setenv("LIMEN_FIRMS_CSV", str(tmp_path / "manca.csv"))
    assert await cli._from_local_csv() == []

    monkeypatch.setenv("LIMEN_FIRMS_CSV", str(csv))
    hotspots = await cli._from_local_csv()
    assert hotspots is not None and {h.source for h in hotspots} == {"VIIRS_SNPP_SP"}


async def test_download_skips_years_before_the_requested_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, int]] = []

    async def _fetch(*, product: Any, year: int, **_k: Any) -> list[FireHotspot]:
        asked.append((product.slug, year))
        return [_hotspot(date(year, 8, 1), source=product.source)]

    monkeypatch.setattr(cli, "fetch_archive_year", _fetch)
    out = await cli._download(ARCHIVE_PRODUCTS, lo=2013, hi=2014, country="Italy")
    assert asked == [("modis", 2013), ("modis", 2014), ("viirs-snpp", 2013), ("viirs-snpp", 2014)]
    assert len(out) == 4


def test_report_names_a_lonely_season_and_the_density(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path)
    text = cli._write_report(
        hotspots=1200,
        events=340,
        country="Italy",
        span=(date(2000, 11, 1), date(2024, 12, 31)),
        agreement=[
            (2024, {"perimeters": 120, "matched": 84}),
            (2023, {"perimeters": 0, "matched": 0}),
        ],
        density={"it-puglia": 800, "it-basilicata": 1500},
    ).read_text(encoding="utf-8")

    assert "Detection in tabella: **2000-11-01 - 2024-12-31**" in text
    assert "| 2024 | 120 | 84 | 70% |" in text
    assert "| 2023 | 0 | 0 | - |" in text
    assert "Una sola stagione" not in text
    assert text.index("it-basilicata") < text.index("it-puglia")

    lonely = cli._write_report(
        hotspots=0,
        events=0,
        country="Italy",
        span=None,
        agreement=[(2024, {"perimeters": 1, "matched": 1})],
        density={},
    ).read_text(encoding="utf-8")
    assert "**vuota**" in lonely
    assert "Una sola stagione confrontabile" in lonely
    assert "Densità storica" not in lonely


class _HistoryDb:
    def __init__(self, *, existing: bool) -> None:
        self.existing = existing
        self.calls: list[str] = []

    def patch(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        @asynccontextmanager
        async def _pool():
            yield

        async def _noop(*_a: Any, **_k: Any) -> None:
            return None

        def _rec(name: str, value: Any) -> Any:
            async def _f(*_a: Any, **_k: Any) -> Any:
                self.calls.append(name)
                return value

            return _f

        class _Conn:
            async def fetchrow(self, _sql: str) -> dict[str, Any]:
                return {"lo": date(2024, 8, 1), "hi": date(2024, 8, 2)}

            async def fetch(self, sql: str) -> list[dict[str, Any]]:
                if "fire_density" in sql:
                    return [{"aoi_id": "it-puglia", "touched": 7}]
                return [{"y": 2024}]

        @asynccontextmanager
        async def _acquire():
            yield _Conn()

        monkeypatch.setattr(cli, "lifespan_pool", _pool)
        monkeypatch.setattr(cli, "run_migrations", _noop)
        monkeypatch.setattr(
            cli, "find_version", _rec("find", SimpleNamespace(id=3) if self.existing else None)
        )
        monkeypatch.setattr(cli, "record_version", _rec("record", 9))
        monkeypatch.setattr(cli, "upsert_hotspots", _rec("upsert", 2))
        monkeypatch.setattr(cli, "count_hotspots", _rec("count", 2))
        monkeypatch.setattr(cli, "list_aoi_ids", _rec("aois", ["it-puglia", "it-molise"]))
        repo = SimpleNamespace(
            rebuild_events=_rec("rebuild", 2),
            refresh_density=_rec("density", 7),
            refresh_perimeter_frp=_rec("frp", 0),
            count_events=_rec("count_events", 2),
            effis_firms_agreement=_rec("agreement", {"perimeters": 3, "matched": 2}),
        )
        monkeypatch.setattr(cli, "fire_events_repo", repo)
        monkeypatch.setattr("limen.data.db.acquire", _acquire)
        monkeypatch.setattr(cli, "REPORTS_DIR", tmp_path)
        monkeypatch.delenv("LIMEN_FIRE_HISTORY_CHECK_YEARS", raising=False)
        monkeypatch.delenv("LIMEN_FIRE_HISTORY_COUNTRY", raising=False)


async def test_run_with_no_hotspots_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none() -> list[FireHotspot]:
        return []

    monkeypatch.setattr(cli, "_from_local_csv", _none)
    assert await cli.run() == 1


async def test_run_ingests_rebuilds_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _HistoryDb(existing=False)
    db.patch(monkeypatch, tmp_path)

    async def _local() -> list[FireHotspot]:
        return [_hotspot(date(2024, 8, 1)), _hotspot(date(2024, 8, 2), lat=40.7)]

    monkeypatch.setattr(cli, "_from_local_csv", _local)

    assert await cli.run() == 0

    assert db.calls.count("density") == 2  # una per AOI seminata
    for step in ("record", "upsert", "rebuild", "frp", "agreement"):
        assert step in db.calls
    text = (tmp_path / "fire_history_italy.md").read_text(encoding="utf-8")
    assert "Detection ingerite: **2**" in text
    assert "| 2024 | 3 | 2 | 67% |" in text
    assert "| `it-puglia` | 7 |" in text


async def test_an_unchanged_archive_skips_writes_but_refreshes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _HistoryDb(existing=True)
    db.patch(monkeypatch, tmp_path)
    monkeypatch.setenv("LIMEN_FIRE_HISTORY_CHECK_YEARS", "2023, 2024")

    async def _local() -> list[FireHotspot]:
        return [_hotspot(date(2024, 8, 1))]

    monkeypatch.setattr(cli, "_from_local_csv", _local)

    assert await cli.run() == 0

    assert not {"record", "upsert", "rebuild", "density", "frp"} & set(db.calls)
    assert db.calls.count("agreement") == 2
    assert (tmp_path / "fire_history_italy.md").exists()
