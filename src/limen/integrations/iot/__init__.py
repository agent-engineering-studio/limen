"""V1.5 — in-situ IoT ingestion.

Public surface assembled incrementally as the V1.5 phase lands:

* :class:`Observation` / :class:`ObservedProperty` — SensorThings-aligned
  Pydantic v2 contract carried over MQTT.
* :func:`run_qc` — range / spike-step / flatline / gap quality control
  pipeline. Sets :class:`QcQuality`.
* :func:`ensure_partition_window` — creates / preserves the rolling
  monthly partition window the ingestor depends on.

The MQTT ingestor and the rollup job land in a follow-up task and are
imported lazily then to keep optional deps (``aiomqtt``) out of every
import path. The whole subsystem is gated by :attr:`Settings.enable_insitu`.
"""

from limen.integrations.iot.partitions import ensure_partition_window
from limen.integrations.iot.qc import QcQuality, run_qc
from limen.integrations.iot.schemas import Observation, ObservedProperty

__all__ = [
    "Observation",
    "ObservedProperty",
    "QcQuality",
    "ensure_partition_window",
    "run_qc",
]
