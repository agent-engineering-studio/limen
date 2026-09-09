"""``limen ingest-events [--hazard landslide|flood]`` — cataloghi datati.

Il truth set contro cui i backtest §2.5 rigiocano la storia. Un pericolo per
sorgente, perché le due sorgenti non si somigliano affatto:

* ``--hazard landslide`` (default) — ITALICA / e-ITALICA: un CSV di **punti**
  datati, scaricabile da un DOI Zenodo fissato. IFFI da solo è un inventario
  senza date.
* ``--hazard flood`` — Copernicus EMS Rapid Mapping: i **poligoni** di
  estensione allagata osservata delle attivazioni italiane. Un allagamento ha
  un'estensione, e su celle da 1 km² il perimetro è ciò che rende il backtest
  misurabile invece di indicativo (#64).

Entrambi idempotenti: l'upsert è per id di catalogo e i download sono in
cache, quindi rieseguire il comando non riscrive nulla e non riscarica nulla.

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
from limen.data.repos import flood_events_repo
from limen.data.repos.landslide_events_repo import LandslideEvent, count_events
from limen.data.repos.landslide_events_repo import upsert_many as events_upsert
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.copernicus_ems.client import (
    ObservationMask,
    ObservedFlood,
    catalogue_provenance,
    fetch_activations,
    fetch_observation_masks,
    fetch_observed_floods,
)

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


async def _run_landslide() -> int:
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
    log.info("ingest_events.done", hazard="landslide", upserted=n, total_in_db=total)
    return 0


def _flood_categories() -> tuple[str, ...]:
    """Categorie EMS da ingerire.

    Default ``Flood,Storm``: la categoria EMS descrive la *causa* e diverse
    alluvioni italiane sono catalogate «Storm» (EMSR928 Lombardia, EMSR930
    Basilicata). Il filtro sui poligoni resta comunque `5-Flood`, quindi
    allargare la categoria non fa entrare eventi di un altro pericolo — fa
    solo guardare in più pacchetti.
    """
    raw = os.getenv("LIMEN_FLOOD_EVENTS_CATEGORIES", "Flood,Storm")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


async def _run_flood() -> int:
    cache = Path(os.getenv("LIMEN_FLOOD_EVENTS_CACHE", "./data/flood_events")).expanduser()
    country = os.getenv("LIMEN_FLOOD_EVENTS_COUNTRY", "Italy")

    try:
        activations = await fetch_activations(country=country, categories=_flood_categories())
        if not activations:
            # Nessuna attivazione è un risultato possibile e non un errore:
            # un paese senza alluvioni mappate nella finestra pubblica.
            log.warning("ingest_events.flood.no_activations", country=country)
            return 0
        polygons: list[ObservedFlood] = []
        masks: list[ObservationMask] = []
        for activation in activations:
            found = await fetch_observed_floods(activation, cache_dir=cache)
            polygons.extend(found)
            # Le maschere si prendono anche quando i poligoni non arrivano:
            # sapere che una zona è stata osservata e trovata asciutta è
            # informazione quanto sapere che si è allagata.
            masks.extend(await fetch_observation_masks(activation.code))
    finally:
        await SharedHttpClient.aclose()

    provenance = catalogue_provenance()
    log.info(
        "ingest_events.flood.parsed",
        polygons=len(polygons),
        activations=len(activations),
        years=sorted({a.event_time.year for a in activations}),
    )
    if not polygons:
        log.warning("ingest_events.flood.no_polygons", note="pacchetti prodotti non leggibili")
        return 1

    async with lifespan_pool():
        await run_migrations()
        n = await flood_events_repo.upsert_many(polygons)
        m = await flood_events_repo.upsert_masks(masks)
        total = await flood_events_repo.count_events()
    log.info(
        "ingest_events.done",
        hazard="flood",
        upserted=n,
        masks=m,
        total_in_db=total,
        source=provenance["source"],
        licence=provenance["licence"],
    )
    return 0


async def run(hazard: str = "landslide") -> int:
    """Dispatcher per pericolo."""
    if hazard == "flood":
        return await _run_flood()
    if hazard in ("landslide", ""):
        return await _run_landslide()
    log.error("ingest_events.unknown_hazard", hazard=hazard)
    return 2


def main() -> int:
    import asyncio

    return asyncio.run(run(os.getenv("LIMEN_INGEST_HAZARD", "landslide")))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
