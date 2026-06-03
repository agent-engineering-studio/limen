"""Weekly job — run the Phase-2 idempotent ISPRA IdroGEO sync."""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations.idrogeo.client import IdroGeoHttpClient
from limen.integrations.idrogeo.sync_job import run_idrogeo_sync
from limen.observability.metrics import get_metrics

log = get_logger(__name__)


async def run_weekly_idrogeo_sync(deps: AppDependencies) -> dict[str, dict[str, object]]:  # noqa: ARG001
    """Run the ISPRA sync over every seeded AOI."""
    aois = await list_aoi_ids()
    if not aois:
        log.info("job.weekly_idrogeo.no_aois")
        return {}
    metrics = get_metrics()
    client = IdroGeoHttpClient()
    out: dict[str, dict[str, object]] = {}
    for aoi_id in aois:
        try:
            result = await run_idrogeo_sync(aoi_id=aoi_id, client=client)
        except Exception as exc:
            log.error(
                "job.weekly_idrogeo.error",
                aoi_id=aoi_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            continue
        out[aoi_id] = dict(result)
        if result.get("skipped"):
            metrics.idrogeo_cache_hits.add(1, {"aoi_id": aoi_id})
        log.info(
            "job.weekly_idrogeo.aoi.done",
            aoi_id=aoi_id,
            **{k: v for k, v in result.items() if k != "version"},
        )
    log.info("job.weekly_idrogeo.done", aois=len(aois))
    return out
