"""Module-level metric instruments used across the codebase.

Importing :mod:`opentelemetry.metrics` doesn't activate exporters by
itself — until :func:`limen.observability.tracing.setup_tracing` is
called, recorded values are silently dropped. That makes the metrics
**safe to use from library code**: tests don't need a real backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from opentelemetry import metrics

_METER = metrics.get_meter("limen", "0.1.0")


@dataclass(slots=True, frozen=True)
class LimenMetrics:
    """Holder for the custom metric instruments used by Limen."""

    risk_score: metrics.Histogram
    alert_dispatched: metrics.Counter
    openmeteo_api_duration: metrics.Histogram
    idrogeo_cache_hits: metrics.Counter
    workflow_executor_duration: metrics.Histogram


def _build() -> LimenMetrics:
    return LimenMetrics(
        risk_score=_METER.create_histogram(
            name="landslide.risk.score",
            description="Per-cell deterministic risk score (0..1)",
            unit="1",
        ),
        alert_dispatched=_METER.create_counter(
            name="landslide.alert.dispatched",
            description="Number of alerts dispatched (or that would have been dispatched in V1).",
            unit="1",
        ),
        openmeteo_api_duration=_METER.create_histogram(
            name="openmeteo.api.duration",
            description="Wall-clock duration of an Open-Meteo client call.",
            unit="s",
        ),
        idrogeo_cache_hits=_METER.create_counter(
            name="idrogeo.cache.hits",
            description="Number of ISPRA IdroGEO sync runs that hit the dataset_versions cache.",
            unit="1",
        ),
        workflow_executor_duration=_METER.create_histogram(
            name="workflow.executor.duration",
            description="Wall-clock duration of a single workflow executor.",
            unit="s",
        ),
    )


_METRICS = _build()


def get_metrics() -> LimenMetrics:
    """Return the process-wide :class:`LimenMetrics` singleton."""
    return _METRICS
