"""Periodic refresh of cell_static_factors from the geodata PostGIS.

This job is the operational complement to ``limen geodata
export-features``: it runs against the operational API's own DSN, so
the per-cell static factors stay in sync with the latest ISPRA mosaic
+ IFFI inventory.

Gated by ``geodata.enable_periodic_export`` — off by default, since
the geodata profile is itself opt-in. With the geodata stack down the
job logs a warning and returns 0 (best-effort, never crashes the
scheduler).
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger

log = get_logger(__name__)


async def run_geodata_export_job(deps: AppDependencies) -> int:
    """Invoke ``geodata.exports.features.export_cell_features``.

    The DSN handed over is the operational API's own DB connection string
    — the exporter reads cells from there and upserts the three numeric
    columns straight back into ``cell_static_factors``. The geodata DB
    DSN comes from the ``GEODATA_DB_DSN`` environment variable.
    """
    if not deps.settings.geodata.enable_periodic_export:
        log.debug("job.geodata_export.skip_disabled")
        return 0

    try:
        from geodata.exports.features import export_cell_features
    except ImportError as exc:
        log.warning(
            "job.geodata_export.skip_unavailable",
            error=str(exc),
            hint="install limen-geodata in the API image to enable this job",
        )
        return 0

    operational_dsn = deps.settings.db.connection_string
    try:
        rc = await export_cell_features(operational_dsn=operational_dsn)
    except Exception as exc:
        log.warning(
            "job.geodata_export.error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0
    log.info("job.geodata_export.done", exit_code=rc)
    return 0
