"""FIRMS hotspot trigger — event-driven monitoring after a wildfire.

Every ``FIRMS__INTERVAL_MINUTES`` the job pulls NASA FIRMS active-fire
detections over the national bbox and persists them. AOIs with at least
``FIRMS__MIN_HOTSPOTS`` detections inside their polygon in the trailing
``FIRMS__TRIGGER_WINDOW_HOURS`` get their monitoring workflow run
immediately: the post-fire amplification of the landslide score matters
most in the days right after the burn, and waiting for the consolidated
EFFIS perimeter costs days.

Same contract as the radar nowcast: FIRMS decides *when* to run, never
*what* to score. Alerts flow through the normal operational path
(escalation, per-cell dedup, channels), and a cooldown skips AOIs that
were assessed recently.

Fail-closed: no ``FIRMS__MAP_KEY`` ⇒ the job is never registered, and
even if invoked directly it returns without touching the network.
"""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.repos.aoi_repo import assessed_within
from limen.data.repos.fire_repo import aoi_hotspot_counts
from limen.integrations.firms import FirmsHttpClient, run_firms_sync

log = get_logger(__name__)


async def run_firms_monitoring(deps: AppDependencies) -> dict[str, int]:
    """Hotspot sweep; returns the hotspot count per triggered AOI."""
    cfg = deps.settings.firms
    if not cfg.active:
        log.info("job.firms.skip", reason="feed inactive (no FIRMS__MAP_KEY)")
        return {}

    client = FirmsHttpClient(
        map_key=cfg.map_key.get_secret_value() if cfg.map_key else "",
        min_confidence=cfg.min_confidence,
        min_confidence_pct=cfg.min_confidence_pct,
        min_frp_mw=cfg.min_frp_mw,
    )
    sync = await run_firms_sync(
        client=client,
        bbox=cfg.bbox,
        sources=cfg.sources,
        day_range=cfg.day_range,
    )
    log.info("job.firms.sync", **{k: v for k, v in sync.items() if k != "version"})

    # Counted from the database, not from the fetched batch: a skipped
    # (unchanged) sync must still be able to trigger an AOI whose
    # detections landed on an earlier poll.
    counts = await aoi_hotspot_counts(
        window_hours=cfg.trigger_window_hours,
        min_hotspots=cfg.min_hotspots,
    )

    triggered: dict[str, int] = {}
    for aoi_id, hotspots in counts.items():
        if await assessed_within(aoi_id, minutes=cfg.cooldown_minutes):
            log.info("job.firms.cooldown", aoi_id=aoi_id, hotspots=hotspots)
            continue
        log.info("job.firms.triggered", aoi_id=aoi_id, hotspots=hotspots)
        try:
            workflow = deps.build_workflow()
            ctx = MonitoringContext(
                aoi_id=aoi_id,
                valuation_time=datetime.now(UTC),
                enable_insitu=deps.settings.enable_insitu,
            )
            result = await workflow.run(ctx)
            triggered[aoi_id] = hotspots
            log.info(
                "job.firms.aoi.done",
                aoi_id=aoi_id,
                cells=len(result.context.cell_results),
                assessment_id=result.context.assessment_id,
            )
        except Exception as exc:  # never bring the scheduler down
            log.error(
                "job.firms.error",
                aoi_id=aoi_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    log.info("job.firms.done", triggered=triggered)
    return triggered
