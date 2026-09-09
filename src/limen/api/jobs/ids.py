"""Identificatori dei job periodici.

In un modulo a sé e non in `registration.py` per rompere un ciclo: la
registrazione importa i job, e un job che vuole tracciarsi (#75) ha bisogno
del proprio identificatore — importarlo da `registration` chiuderebbe
l'anello. `registration` li ri-esporta, così gli import esistenti non cambiano.
"""

from __future__ import annotations

JOB_HOURLY_MONITORING = "limen-hourly-monitoring"
JOB_FORECAST_MONITORING = "limen-forecast-monitoring"
JOB_FORECAST_HISTORY = "limen-forecast-history"
JOB_DAILY_REPORT = "limen-daily-report"
JOB_NOWCAST_MONITORING = "limen-nowcast-monitoring"
JOB_FIRMS_MONITORING = "limen-firms-monitoring"
JOB_WEEKLY_IDROGEO = "limen-weekly-idrogeo"
JOB_ALERT_DIGEST = "limen-alert-digest"
JOB_CACHE_CLEANUP = "limen-cache-cleanup"
JOB_PARTITIONS = "limen-partitions"
JOB_IOT_ROLLUP = "limen-iot-rollup"
JOB_IOT_PARTITION_ROLLOVER = "limen-iot-partition-rollover"
JOB_DRIFT_MONITOR = "limen-drift-monitor"
JOB_GEODATA_EXPORT = "limen-geodata-export"
JOB_HTML_REPORT = "limen-html-report"


__all__ = [
    "JOB_ALERT_DIGEST",
    "JOB_CACHE_CLEANUP",
    "JOB_DAILY_REPORT",
    "JOB_DRIFT_MONITOR",
    "JOB_FIRMS_MONITORING",
    "JOB_FORECAST_HISTORY",
    "JOB_FORECAST_MONITORING",
    "JOB_GEODATA_EXPORT",
    "JOB_HOURLY_MONITORING",
    "JOB_HTML_REPORT",
    "JOB_IOT_PARTITION_ROLLOVER",
    "JOB_IOT_ROLLUP",
    "JOB_NOWCAST_MONITORING",
    "JOB_PARTITIONS",
    "JOB_WEEKLY_IDROGEO",
]
