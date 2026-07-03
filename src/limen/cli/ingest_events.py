"""``limen ingest-events`` — load the ITALICA / e-ITALICA event catalogue.

Reads the ITALICA CSV (semicolon-delimited, EPSG:4326 lon/lat + UTC date)
into ``landslide_events``. This is the dated truth set the §2.5 backtest
replays against — IFFI on its own is an undated inventory.

Source resolution (for reproducible init on a fresh machine):
1. ``LIMEN_ITALICA_CSV`` — explicit local path wins (offline / custom file);
2. otherwise download e-ITALICA v4 from the pinned Zenodo DOI
   (10.5281/zenodo.14204473, CC-BY-4.0) into ``LIMEN_DATA_DIR`` and cache it.

Idempotent: the download is skipped when the cached file already exists, and
the upsert is keyed by catalogue id.
"""

from __future__ import annotations

import csv
import os
from datetime import UTC, datetime
from pathlib import Path

from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.landslide_events_repo import LandslideEvent, count_events
from limen.data.repos.landslide_events_repo import upsert_many as events_upsert
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

# Pinned e-ITALICA v4 (Zenodo DOI 10.5281/zenodo.14204473, CC-BY-4.0).
# The download lives under the /api/records/ path — the bare /records/ path
# returns 404 for the /content file endpoint.
_ITALICA_URL = "https://zenodo.org/api/records/14204473/files/ITALICA_v4.csv/content"
_ITALICA_FILENAME = "ITALICA_v4.csv"


async def _resolve_csv() -> Path | None:
    """Return the ITALICA CSV path, downloading from Zenodo if not local."""
    explicit = os.getenv("LIMEN_ITALICA_CSV", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            log.error("ingest_events.csv_missing", path=str(path))
            return None
        return path

    data_dir = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser()
    dest = data_dir / _ITALICA_FILENAME
    if dest.is_file() and dest.stat().st_size > 0:
        log.info("ingest_events.cache_hit", path=str(dest))
        return dest

    url = os.getenv("LIMEN_ITALICA_URL", _ITALICA_URL)
    log.info("ingest_events.download", url=url, dest=str(dest))
    resp = await fetch_with_retry("GET", url, client=await SharedHttpClient.get())
    data_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    log.info("ingest_events.downloaded", path=str(dest), bytes=len(resp.content))
    return dest


def _f(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_utc(raw: str | None) -> datetime | None:
    """Parse ITALICA ``utc_date`` (``DD/MM/YYYY HH:MM`` or ``DD/MM/YYYY``)."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_rows(path: Path) -> list[LandslideEvent]:
    events: list[LandslideEvent] = []
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            rid = (row.get("id") or "").strip()
            lon = _f(row.get("lon"))
            lat = _f(row.get("lat"))
            when = _parse_utc(row.get("utc_date"))
            if not rid or lon is None or lat is None or when is None:
                skipped += 1
                continue
            events.append(
                LandslideEvent(
                    id=rid,
                    source=(row.get("information_source") or "").strip() or "unknown",
                    event_time=when,
                    geom=Point(lon, lat),
                    temporal_accuracy=(row.get("temporal_accuracy") or "").strip() or None,
                    geographic_accuracy=(row.get("geographic_accuracy") or "").strip() or None,
                    landslide_type=(row.get("landslide_type") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    province=(row.get("province") or "").strip() or None,
                    municipality=(row.get("municipality") or "").strip() or None,
                    elevation_m=_f(row.get("elevation")),
                    slope_deg=_f(row.get("slope")),
                    duration_h=_f(row.get("duration")),
                    cumulated_rainfall_mm=_f(row.get("cumulated_rainfall")),
                    attributes={"catalogue": "italica", "land_cover": row.get("land_cover")},
                )
            )
    if skipped:
        log.warning("ingest_events.rows_skipped", skipped=skipped, note="missing id/lon/lat/date")
    return events


async def run() -> int:
    try:
        path = await _resolve_csv()
    finally:
        await SharedHttpClient.aclose()
    if path is None:
        return 1

    events = _parse_rows(path)
    log.info("ingest_events.parsed", path=str(path), events=len(events))

    async with lifespan_pool():
        await run_migrations()
        n = await events_upsert(events)
        total = await count_events()
    log.info("ingest_events.done", upserted=n, total_in_db=total)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
