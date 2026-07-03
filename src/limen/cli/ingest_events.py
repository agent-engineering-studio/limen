"""``limen ingest-events`` — load the ITALICA / e-ITALICA event catalogue.

Reads the ITALICA CSV (semicolon-delimited, EPSG:4326 lon/lat + UTC date)
into ``landslide_events``. This is the dated truth set the §2.5 backtest
replays against — IFFI on its own is an undated inventory.

Opt-in: set ``LIMEN_ITALICA_CSV`` to the downloaded CSV path (e.g. the
e-ITALICA ``ITALICA_v4.csv`` from Zenodo, CC-BY-4.0). Unset ⇒ logged skip,
no writes. Idempotent: re-running upserts by catalogue id.
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

log = get_logger(__name__)


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
    raw_path = os.getenv("LIMEN_ITALICA_CSV", "").strip()
    if not raw_path:
        log.warning(
            "ingest_events.skip_no_csv",
            note="set LIMEN_ITALICA_CSV to the ITALICA/e-ITALICA CSV path",
        )
        return 0

    path = Path(raw_path).expanduser()
    if not path.is_file():
        log.error("ingest_events.csv_missing", path=str(path))
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
