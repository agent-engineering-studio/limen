"""INGV ingestion job: events + optional ShakeMap raster bytes.

Orchestrates :class:`IngvHttpClient` and writes to:

* ``seismic_events`` (per event)
* ``raster_refs`` + ``ObjectStore`` (per event with a ShakeMap)

Idempotent: events are upserted by INGV ``eventID``; the ShakeMap path
written into the ObjectStore is deterministic, so re-running overwrites
the same key.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from shapely.geometry import Point, box

from limen.core.logging import get_logger
from limen.data.object_store import ObjectStore, build_object_store
from limen.data.repos.raster_refs_repo import sha256_hex
from limen.data.repos.raster_refs_repo import upsert as upsert_raster_ref
from limen.data.repos.seismic_repo import SeismicEvent, count_events, upsert_event
from limen.integrations.ingv.shakemap_client import IngvHttpClient

log = get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_MIN_MAGNITUDE = 3.5


def _shakemap_key(event_id: str) -> str:
    """Deterministic ObjectStore key for the ShakeMap of a given event."""
    return f"shakemap/{event_id}/grid.xml"


def _parse_feature(feat: dict[str, Any]) -> SeismicEvent | None:
    """Convert one FDSN GeoJSON feature to a :class:`SeismicEvent`."""
    props = dict(feat.get("properties") or {})
    geom_field = feat.get("geometry") or {}
    coords = geom_field.get("coordinates")
    if not coords or len(coords) < 2:
        log.warning("ingv.event.skip", reason="no coordinates", feature_id=feat.get("id"))
        return None

    event_id = str(feat.get("id") or props.get("eventID") or props.get("eventId") or "").strip()
    if not event_id:
        log.warning("ingv.event.skip", reason="no event id")
        return None

    # FDSN GeoJSON coords: [lon, lat, depth_km] (depth often negative or null)
    lon, lat = float(coords[0]), float(coords[1])
    depth_km: float | None = float(coords[2]) if len(coords) > 2 and coords[2] is not None else None

    time_str = props.get("time") or props.get("origintime") or props.get("origin_time")
    if not time_str:
        log.warning("ingv.event.skip", reason="no time", event_id=event_id)
        return None
    origin_time = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
    if origin_time.tzinfo is None:
        origin_time = origin_time.replace(tzinfo=UTC)

    mag = props.get("mag")
    if mag is None:
        log.warning("ingv.event.skip", reason="no magnitude", event_id=event_id)
        return None
    magnitude = float(mag)

    return SeismicEvent(
        id=event_id,
        origin_time=origin_time,
        magnitude=magnitude,
        magnitude_type=props.get("magType") or props.get("magnitude_type"),
        depth_km=depth_km,
        geom=Point(lon, lat),
        region=props.get("place") or props.get("region") or props.get("eventLocationName"),
        attributes=props,
    )


async def run_ingv_sync(
    *,
    bbox: tuple[float, float, float, float],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
    client: IngvHttpClient | None = None,
    object_store: ObjectStore | None = None,
) -> dict[str, int]:
    """Fetch events for the trailing ``lookback_days`` and upsert them.

    For events with a published ShakeMap, fetch ``grid.xml``, write it
    to the object store, and create a :func:`raster_refs.upsert` row that
    the event row points at via ``raster_ref_id``.

    Returns ``{"events": n, "shakemaps": k}``.
    """
    cli = client or IngvHttpClient()
    store = object_store or build_object_store()

    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)

    features = list(
        await cli.fetch_events(bbox=bbox, start=start, end=end, min_magnitude=min_magnitude)
    )
    log.info("ingv.sync.features", count=len(features))

    events = 0
    shakemaps = 0
    bbox_geom = box(*bbox)

    for feat in features:
        event = _parse_feature(feat)
        if event is None:
            continue

        # Try to attach a ShakeMap if one exists.
        grid_bytes = await cli.fetch_shakemap_grid(event.id)
        raster_ref_id: int | None = None
        shakemap_path: str | None = None
        if grid_bytes:
            key = _shakemap_key(event.id)
            location = await store.put(key, grid_bytes, content_type="application/xml")
            ref_id = await upsert_raster_ref(
                kind="shakemap_grid",
                path=key,
                bbox=bbox_geom,
                crs="EPSG:4326",
                checksum_sha256=sha256_hex(grid_bytes),
                size_bytes=len(grid_bytes),
                metadata={
                    "event_id": event.id,
                    "magnitude": event.magnitude,
                    "object_store_location": location,
                },
            )
            raster_ref_id = ref_id
            shakemap_path = key
            shakemaps += 1
            log.info("ingv.shakemap.stored", event_id=event.id, key=key, ref_id=ref_id)

        if raster_ref_id is not None or shakemap_path is not None:
            event = SeismicEvent(
                id=event.id,
                origin_time=event.origin_time,
                magnitude=event.magnitude,
                magnitude_type=event.magnitude_type,
                depth_km=event.depth_km,
                geom=event.geom,
                region=event.region,
                shakemap_path=shakemap_path,
                raster_ref_id=raster_ref_id,
                dataset_version_id=event.dataset_version_id,
                attributes=event.attributes,
            )

        await upsert_event(event)
        events += 1

    total_after = await count_events()
    log.info("ingv.sync.done", events=events, shakemaps=shakemaps, total=total_after)
    return {"events": events, "shakemaps": shakemaps}
