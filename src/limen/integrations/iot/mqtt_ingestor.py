"""MQTT ingestor — subscribes to ``limen/v1/+/+/+/+/obs``.

For each message the pipeline is:

1. **Parse** — strict JSON → :class:`Observation` (rejects unknown
   fields, requires the timezone-aware ``phenomenon_time``).
2. **Topic check** — the trailing ``thing`` segment must match the
   payload's ``thing_id``.
3. **Resolve** — look up the :class:`SensorDevice` (cell binding +
   calibration). Unknown / quarantined devices are dropped (logged).
4. **Calibrate** — convert the raw reading to the canonical UCUM unit
   using the device's calibration JSON (``scale``, ``offset``, ``unit``).
5. **QC** — :func:`run_qc` produces the :class:`QcQuality` label.
6. **Persist** — :func:`sensor_observations_repo.insert` writes one row;
   :func:`sensor_devices_repo.touch_last_seen` records liveness.

The ingestor is a long-running asyncio task. The lifespan owns it and
cancels it on shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiomqtt
import structlog
from pydantic import ValidationError

from limen.config.settings import IotSettings
from limen.core.logging import get_logger
from limen.data.repos import sensor_devices_repo, sensor_observations_repo
from limen.data.repos.sensor_observations_repo import SensorObservation
from limen.integrations.iot.qc import QcQuality, run_qc
from limen.integrations.iot.schemas import (
    CANONICAL_UNITS,
    Observation,
    ObservedProperty,
)

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


# Per-property fallback noise scale, used only when the device's
# calibration JSON doesn't override it. Velocity gets the YAML's
# ``kinematic.sigma_v`` injected at construction time.
_DEFAULT_SIGMA: dict[ObservedProperty, float] = {
    ObservedProperty.RAINFALL: 0.5,
    ObservedProperty.PORE_PRESSURE: 5.0,
    ObservedProperty.SOIL_MOISTURE: 0.02,
    ObservedProperty.DISPLACEMENT: 1.0,
    ObservedProperty.VELOCITY: 3.0,
    ObservedProperty.ACCELERATION: 0.5,
}


@dataclass(frozen=True, slots=True)
class CalibratedObservation:
    """Result of applying the device calibration to a raw payload."""

    observation: Observation
    canonical_value: float


def _topic_thing_segment(topic: str) -> str | None:
    """Return the ``{thing}`` segment, or ``None`` if the shape is wrong."""
    parts = topic.split("/")
    # limen / v1 / region / site / thing / datastream / obs
    if len(parts) != 7 or parts[0] != "limen" or parts[-1] != "obs":
        return None
    return parts[4]


def _calibrate(observation: Observation, calibration: dict[str, Any]) -> float:
    """Apply ``scale`` + ``offset`` from the device calibration JSON.

    The default identity transform (1.0 / 0.0) is used when the device
    doesn't ship calibration for this property.
    """
    per_property = calibration.get(observation.observed_property.value, {})
    scale = float(per_property.get("scale", 1.0))
    offset = float(per_property.get("offset", 0.0))
    return observation.result_value * scale + offset


class MqttIngestor:
    """Subscribe to MQTT, process incoming observations, persist them."""

    def __init__(self, settings: IotSettings, *, sigma_v: float | None = None) -> None:
        self._settings = settings
        self._sigma_overrides: dict[ObservedProperty, float] = {}
        if sigma_v is not None:
            self._sigma_overrides[ObservedProperty.VELOCITY] = float(sigma_v)
            self._sigma_overrides[ObservedProperty.DISPLACEMENT] = float(sigma_v)
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    @property
    def settings(self) -> IotSettings:
        return self._settings

    # ----- lifecycle -----
    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("MqttIngestor already started")
        self._task = asyncio.create_task(self._run(), name="limen-iot-ingestor")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopped.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None

    # ----- run loop -----
    async def _run(self) -> None:
        password = (
            self._settings.password.get_secret_value()
            if self._settings.password is not None
            else None
        )
        while not self._stopped.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=self._settings.broker_host,
                    port=self._settings.broker_port,
                    username=self._settings.username,
                    password=password,
                    identifier=self._settings.client_id,
                    tls_params=aiomqtt.TLSParameters() if self._settings.broker_tls else None,
                ) as client:
                    await client.subscribe(self._settings.subscribe_pattern, qos=1)
                    _log.info(
                        "iot.ingestor.connected",
                        broker=self._settings.broker_host,
                        pattern=self._settings.subscribe_pattern,
                    )
                    async for message in client.messages:
                        await self._handle_message(
                            topic=str(message.topic),
                            payload=bytes(message.payload),
                        )
            except asyncio.CancelledError:
                raise
            except (aiomqtt.MqttError, OSError, TimeoutError) as exc:
                _log.warning(
                    "iot.ingestor.disconnected",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(5.0)

    # ----- per-message pipeline -----
    async def _handle_message(self, *, topic: str, payload: bytes) -> None:
        thing_segment = _topic_thing_segment(topic)
        if thing_segment is None:
            _log.warning("iot.ingestor.bad_topic", topic=topic)
            return

        observation = self._parse(payload)
        if observation is None:
            return

        if observation.thing_id != thing_segment:
            _log.warning(
                "iot.ingestor.thing_mismatch",
                topic_thing=thing_segment,
                payload_thing=observation.thing_id,
            )
            return

        device = await sensor_devices_repo.get_device(observation.thing_id)
        if device is None:
            _log.warning("iot.ingestor.unknown_device", thing_id=observation.thing_id)
            return
        if device.status == "quarantined":
            _log.info("iot.ingestor.quarantined_drop", thing_id=device.id)
            return

        canonical_value = _calibrate(observation, device.calibration)
        canonical = observation.model_copy(
            update={
                "result_value": canonical_value,
                "result_unit": CANONICAL_UNITS[observation.observed_property],
            }
        )

        quality = await self._run_qc(canonical)
        obs_row = SensorObservation(
            device_id=device.id,
            observed_property=canonical.observed_property,
            phenomenon_time=canonical.phenomenon_time,
            result_value=canonical.result_value,
            result_unit=canonical.result_unit,
            raw_value=observation.result_value,
            quality=quality,
            metadata=dict(observation.metadata),
        )

        try:
            await sensor_observations_repo.insert(obs_row)
        except Exception as exc:
            _log.error(
                "iot.ingestor.persist_error",
                error=str(exc),
                error_type=type(exc).__name__,
                thing_id=device.id,
            )
            return

        await sensor_devices_repo.touch_last_seen(device.id, at=canonical.phenomenon_time)
        _log.debug(
            "iot.ingestor.persisted",
            thing_id=device.id,
            property=canonical.observed_property.value,
            quality=quality.value,
        )

    def _parse(self, payload: bytes) -> Observation | None:
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            _log.warning("iot.ingestor.bad_payload", error=str(exc))
            return None
        try:
            return Observation.model_validate_json(text)
        except ValidationError as exc:
            _log.warning("iot.ingestor.validation_error", error=str(exc))
            return None

    async def _run_qc(self, observation: Observation) -> QcQuality:
        latest = await sensor_observations_repo.latest_for_datastream(
            observation.thing_id, observation.observed_property
        )
        previous_value = latest.result_value if latest is not None else None
        previous_ts: datetime | None = latest.phenomenon_time if latest is not None else None
        recent = await sensor_observations_repo.recent_values(
            observation.thing_id,
            observation.observed_property,
            limit=max(self._settings.flatline_min_samples, 1),
        )
        sigma = self._sigma_overrides.get(
            observation.observed_property,
            _DEFAULT_SIGMA[observation.observed_property],
        )
        return run_qc(
            observation,
            previous_value=previous_value,
            previous_timestamp=previous_ts,
            recent_values=recent,
            sigma=sigma,
            settings=self._settings,
        )


async def iter_messages(
    client: aiomqtt.Client,
) -> AsyncIterator[aiomqtt.Message]:
    """Thin wrapper for tests that want to drive the ingestor manually."""
    async for message in client.messages:
        yield message


__all__ = ["CalibratedObservation", "MqttIngestor", "iter_messages"]
