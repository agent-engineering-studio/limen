"""Register Limen's periodic jobs on an :class:`AsyncScheduler`.

Idempotent: each job has a stable ``id`` so re-running ``register_jobs``
(e.g. after a lifespan restart in tests) replaces the previous schedule
rather than stacking.
"""

from __future__ import annotations

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from limen.api.dependencies import AppDependencies
from limen.api.jobs.cache_cleanup import run_cache_cleanup_job
from limen.api.jobs.daily_report import run_daily_report
from limen.api.jobs.drift_monitor import run_drift_monitor_job
from limen.api.jobs.forecast_monitoring import run_forecast_monitoring
from limen.api.jobs.geodata_export import run_geodata_export_job
from limen.api.jobs.hourly_monitoring import run_hourly_monitoring
from limen.api.jobs.html_report import run_html_report
from limen.api.jobs.iot_partition_rollover import run_iot_partition_rollover_job
from limen.api.jobs.iot_rollup import run_iot_rollup_job
from limen.api.jobs.nowcast_monitoring import run_nowcast_monitoring
from limen.api.jobs.weekly_idrogeo_sync import run_weekly_idrogeo_sync
from limen.config.settings import SchedulerBackend
from limen.core.logging import get_logger

log = get_logger(__name__)

JOB_HOURLY_MONITORING = "limen-hourly-monitoring"
JOB_FORECAST_MONITORING = "limen-forecast-monitoring"
JOB_DAILY_REPORT = "limen-daily-report"
JOB_NOWCAST_MONITORING = "limen-nowcast-monitoring"
JOB_WEEKLY_IDROGEO = "limen-weekly-idrogeo"
JOB_CACHE_CLEANUP = "limen-cache-cleanup"
JOB_IOT_ROLLUP = "limen-iot-rollup"
JOB_IOT_PARTITION_ROLLOVER = "limen-iot-partition-rollover"
JOB_DRIFT_MONITOR = "limen-drift-monitor"
JOB_GEODATA_EXPORT = "limen-geodata-export"
JOB_HTML_REPORT = "limen-html-report"


async def register_jobs(scheduler: AsyncScheduler, deps: AppDependencies) -> list[str]:
    """Schedule every Limen periodic job. Returns the list of job ids registered."""
    cfg = deps.settings.scheduler
    registered: list[str] = []

    if cfg.enable_hourly_monitoring:
        await scheduler.add_schedule(
            run_hourly_monitoring,
            args=(deps,),
            trigger=IntervalTrigger(minutes=cfg.hourly_monitoring_minutes),
            id=JOB_HOURLY_MONITORING,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_HOURLY_MONITORING)
        log.info(
            "scheduler.registered",
            job=JOB_HOURLY_MONITORING,
            interval_minutes=cfg.hourly_monitoring_minutes,
        )

    if deps.settings.forecast.enabled:
        await scheduler.add_schedule(
            run_forecast_monitoring,
            args=(deps,),
            trigger=IntervalTrigger(hours=deps.settings.forecast.interval_hours),
            id=JOB_FORECAST_MONITORING,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_FORECAST_MONITORING)
        log.info(
            "scheduler.registered",
            job=JOB_FORECAST_MONITORING,
            interval_hours=deps.settings.forecast.interval_hours,
            horizon_hours=deps.settings.forecast.horizon_hours,
        )

    if deps.settings.report.enabled:
        await scheduler.add_schedule(
            run_daily_report,
            args=(deps,),
            trigger=CronTrigger(hour=deps.settings.report.hour_utc, minute=0),
            id=JOB_DAILY_REPORT,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_DAILY_REPORT)
        log.info(
            "scheduler.registered",
            job=JOB_DAILY_REPORT,
            hour_utc=deps.settings.report.hour_utc,
        )

    if deps.settings.report.html_enabled:
        await scheduler.add_schedule(
            run_html_report,
            args=(deps,),
            trigger=IntervalTrigger(hours=deps.settings.report.html_interval_hours),
            id=JOB_HTML_REPORT,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_HTML_REPORT)
        log.info(
            "scheduler.registered",
            job=JOB_HTML_REPORT,
            interval_hours=deps.settings.report.html_interval_hours,
        )

    if deps.settings.nowcast.enabled:
        await scheduler.add_schedule(
            run_nowcast_monitoring,
            args=(deps,),
            trigger=IntervalTrigger(minutes=deps.settings.nowcast.interval_minutes),
            id=JOB_NOWCAST_MONITORING,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_NOWCAST_MONITORING)
        log.info(
            "scheduler.registered",
            job=JOB_NOWCAST_MONITORING,
            interval_minutes=deps.settings.nowcast.interval_minutes,
            min_intensity_mmh=deps.settings.nowcast.min_intensity_mmh,
        )

    if cfg.enable_weekly_idrogeo:
        await scheduler.add_schedule(
            run_weekly_idrogeo_sync,
            args=(deps,),
            trigger=CronTrigger(day_of_week="mon", hour=3, minute=15),
            id=JOB_WEEKLY_IDROGEO,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_WEEKLY_IDROGEO)
        log.info(
            "scheduler.registered",
            job=JOB_WEEKLY_IDROGEO,
            cron="mon 03:15",
        )

    if cfg.cache_cleanup is SchedulerBackend.APSCHEDULER:
        await scheduler.add_schedule(
            run_cache_cleanup_job,
            args=(deps,),
            trigger=IntervalTrigger(seconds=cfg.cache_cleanup_interval_seconds),
            id=JOB_CACHE_CLEANUP,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_CACHE_CLEANUP)
        log.info(
            "scheduler.registered",
            job=JOB_CACHE_CLEANUP,
            interval_seconds=cfg.cache_cleanup_interval_seconds,
        )

    if deps.settings.enable_insitu:
        await scheduler.add_schedule(
            run_iot_rollup_job,
            args=(deps,),
            trigger=IntervalTrigger(minutes=deps.settings.iot.rollup_minutes),
            id=JOB_IOT_ROLLUP,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_IOT_ROLLUP)
        log.info(
            "scheduler.registered",
            job=JOB_IOT_ROLLUP,
            interval_minutes=deps.settings.iot.rollup_minutes,
        )

        await scheduler.add_schedule(
            run_iot_partition_rollover_job,
            args=(deps,),
            trigger=CronTrigger(day=2, hour=2, minute=0),
            id=JOB_IOT_PARTITION_ROLLOVER,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_IOT_PARTITION_ROLLOVER)
        log.info(
            "scheduler.registered",
            job=JOB_IOT_PARTITION_ROLLOVER,
            cron="day 02 02:00",
        )

    if deps.settings.monitoring.enable_drift_monitoring:
        await scheduler.add_schedule(
            run_drift_monitor_job,
            args=(deps,),
            trigger=IntervalTrigger(hours=deps.settings.monitoring.drift_check_hours),
            id=JOB_DRIFT_MONITOR,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_DRIFT_MONITOR)
        log.info(
            "scheduler.registered",
            job=JOB_DRIFT_MONITOR,
            interval_hours=deps.settings.monitoring.drift_check_hours,
        )

    if deps.settings.geodata.enable_periodic_export:
        await scheduler.add_schedule(
            run_geodata_export_job,
            args=(deps,),
            trigger=IntervalTrigger(hours=deps.settings.geodata.export_features_hours),
            id=JOB_GEODATA_EXPORT,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_GEODATA_EXPORT)
        log.info(
            "scheduler.registered",
            job=JOB_GEODATA_EXPORT,
            interval_hours=deps.settings.geodata.export_features_hours,
        )

    return registered
