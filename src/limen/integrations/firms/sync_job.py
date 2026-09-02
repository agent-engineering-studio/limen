"""FIRMS ingestion job: fetch active-fire hotspots and upsert.

Idempotency follows the house pattern: a SHA-256 over the canonical
representation of the fetched detections becomes the
``dataset_versions('nasa', 'firms_hotspots', <hash>)`` version. A second
run over an unchanged FIRMS window finds that row and **skips all
writes** — which is the normal case, since the interval between polls is
shorter than the NRT publication cadence.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any

from limen.core.logging import get_logger
from limen.data.repos.dataset_versions_repo import content_hash
from limen.data.repos.dataset_versions_repo import find as find_version
from limen.data.repos.dataset_versions_repo import record as record_version
from limen.data.repos.fire_repo import FireHotspot, count_hotspots, upsert_hotspots

if TYPE_CHECKING:
    from collections.abc import Sequence

    from limen.integrations.firms.client import FirmsHttpClient

log = get_logger(__name__)

SOURCE = "nasa"
DATASET = "firms_hotspots"


def _hotspots_to_hash(hotspots: Sequence[FireHotspot]) -> str:
    """Content hash over the natural key + payload of every detection.

    Serialised per detection and sorted as text, so the hash is
    independent of the per-source fetch order.
    """
    canonical = sorted(
        json.dumps(
            [
                h.source,
                h.acq_date.isoformat(),
                h.acq_time,
                h.latitude,
                h.longitude,
                h.frp_mw,
                h.confidence,
            ],
            default=str,
        )
        for h in hotspots
    )
    return content_hash("\n".join(canonical).encode("utf-8"))


async def run_firms_sync(
    *,
    client: FirmsHttpClient,
    bbox: tuple[float, float, float, float],
    sources: Sequence[str],
    day_range: int = 1,
    on_date: date | None = None,
) -> dict[str, Any]:
    """Fetch hotspots for ``bbox`` and upsert them.

    Returns ``{"skipped": True, ...}`` when the fetched window is
    byte-identical to a previously ingested one, otherwise the counters.
    """
    hotspots = list(
        await client.fetch_hotspots(
            bbox=bbox, sources=sources, day_range=day_range, on_date=on_date
        )
    )
    if not hotspots:
        # Includes the degraded case: no detections, nothing to version.
        log.info("firms.sync.empty", sources=list(sources), day_range=day_range)
        return {"skipped": False, "hotspots": 0, "total": await count_hotspots()}

    version = _hotspots_to_hash(hotspots)
    existing = await find_version(SOURCE, DATASET, version)
    if existing is not None:
        log.info(
            "firms.sync.skip",
            reason="content unchanged",
            version=version,
            version_id=existing.id,
            fetched=len(hotspots),
        )
        return {
            "skipped": True,
            "version": version,
            "version_id": existing.id,
            "hotspots": 0,
        }

    version_id = await record_version(
        source=SOURCE,
        dataset=DATASET,
        version=version,
        metadata={
            "bbox": list(bbox),
            "sources": list(sources),
            "day_range": day_range,
            "on_date": on_date.isoformat() if on_date is not None else None,
            "hotspot_count": len(hotspots),
        },
    )
    written = await upsert_hotspots(hotspots, dataset_version_id=version_id)
    total = await count_hotspots()
    log.info(
        "firms.sync.done",
        hotspots=written,
        total=total,
        version=version,
        version_id=version_id,
    )
    return {
        "skipped": False,
        "version": version,
        "version_id": version_id,
        "hotspots": written,
        "total": total,
    }
