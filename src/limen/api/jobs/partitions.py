"""Hot-table partition maintenance + retention.

Its own job rather than a step inside the cache cleanup, for two reasons the
review of #82 surfaced: the cleanup job is not registered at all under
``SCHEDULER__CACHE_CLEANUP=pg_cron``, and it returns early whenever the cache
backend misbehaves. Either one would leave the partitions uncreated, and a
missing partition sends every write to ``*_default`` where retention cannot
reach it.

Retention is a partition drop, not a delete: ``risk_assessments`` grows
~15 GB/day and ``model_runs`` ~1 GB/day, and DELETE batches over tables that
size leave bloat behind and never catch up.

La purga di ``job_runs`` (#75) vive qui e **non** nel cache-cleanup, dove la
issue la collocava, per la prima delle due ragioni sopra: quel job non viene
registrato sotto pg_cron, e una retention che non gira su metà dei deployment
non è una retention. Lì è un DELETE e non un drop di partizione: `job_runs`
cresce di poche migliaia di righe al giorno, non dei gigabyte delle tabelle
calde, e partizionarla sarebbe complessità per niente.
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.data.repos import job_runs_repo, partitions_repo

log = get_logger(__name__)


async def run_partitions_job(deps: AppDependencies) -> dict[str, int]:
    """Create the upcoming partitions, then drop the expired ones."""
    scoring = deps.settings.scoring
    dropped: dict[str, int] = {}
    try:
        created = await partitions_repo.ensure()
        await partitions_repo.warn_on_default_rows()
        dropped["model_runs"] = await partitions_repo.drop_expired(
            "model_runs", scoring.model_runs_retention_days
        )
        # Retention for risk_assessments had never actually run: the previous
        # DELETE-based purge was defined but no caller invoked it, so the
        # biggest table in the system grew unbounded.
        dropped["risk_assessments"] = await partitions_repo.drop_expired(
            "risk_assessments", scoring.assessments_retention_days
        )
        dropped["job_runs"] = await job_runs_repo.purge_older_than(
            deps.settings.scheduler.job_runs_retention_days
        )
    except Exception as exc:
        log.error(
            "job.partitions.error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {}
    if any(created.values()) or any(dropped.values()):
        log.info("job.partitions.done", created=created, dropped=dropped)
    return dropped
