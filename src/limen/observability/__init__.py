"""OpenTelemetry tracing + metrics wiring.

Public surface:

* :func:`setup_tracing` — registers the FastAPI / asyncpg / httpx
  instrumentors and an OTLP HTTP exporter (configurable endpoint).
* :data:`metrics` — module-level :mod:`opentelemetry.metrics` Counters
  and Histograms used across the workflow (see §3.9):

  - ``landslide.risk.score``         (histogram, 0..1)
  - ``landslide.alert.dispatched``   (counter)
  - ``openmeteo.api.duration``       (histogram, seconds)
  - ``idrogeo.cache.hits``           (counter)
  - ``workflow.executor.duration``   (histogram, seconds)

All of this is **best-effort**: if OTel imports fail or the exporter
URL is unreachable the API keeps serving traffic. Observability is
optional, not load-bearing.
"""

from limen.observability.metrics import LimenMetrics, get_metrics
from limen.observability.tracing import setup_tracing

__all__ = ["LimenMetrics", "get_metrics", "setup_tracing"]
