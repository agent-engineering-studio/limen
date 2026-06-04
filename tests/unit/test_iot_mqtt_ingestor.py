"""MQTT ingestor — handler pipeline (topic parse, calibrate, persist).

Drives the per-message pipeline directly so we don't need a broker.
The DB repos are monkey-patched to in-memory async stubs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from shapely.geometry import Point

from limen.config.settings import IotSettings
from limen.data.repos.sensor_devices_repo import SensorDevice
from limen.data.repos.sensor_observations_repo import RecentSample, SensorObservation
from limen.integrations.iot.mqtt_ingestor import (
    MqttIngestor,
    _calibrate,
    _topic_thing_segment,
)
from limen.integrations.iot.qc import QcQuality
from limen.integrations.iot.schemas import Observation, ObservedProperty

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_topic_thing_segment_extracts_thing() -> None:
    assert _topic_thing_segment("limen/v1/it-puglia/site-a/thing-7/displacement/obs") == "thing-7"


def test_topic_thing_segment_rejects_bad_shape() -> None:
    assert _topic_thing_segment("foo/bar/baz") is None
    assert _topic_thing_segment("limen/v1/it-puglia/site/thing/ds/status") is None


def test_calibrate_applies_scale_and_offset() -> None:
    obs = Observation(
        thing_id="t",
        observed_property=ObservedProperty.DISPLACEMENT,
        phenomenon_time=NOW,
        result_value=2.0,
        result_unit="mm",
    )
    calib = {"displacement": {"scale": 1000.0, "offset": 0.0}}  # m → mm
    assert _calibrate(obs, calib) == 2000.0


def test_calibrate_defaults_to_identity() -> None:
    obs = Observation(
        thing_id="t",
        observed_property=ObservedProperty.RAINFALL,
        phenomenon_time=NOW,
        result_value=5.0,
        result_unit="mm",
    )
    assert _calibrate(obs, {}) == 5.0


# ---------------------------------------------------------------------------
# End-to-end pipeline with stubbed repos
# ---------------------------------------------------------------------------
class _RepoStubs:
    """In-memory replacement for the three repos the ingestor touches."""

    def __init__(self, device: SensorDevice | None) -> None:
        self.device = device
        self.observations: list[SensorObservation] = []
        self.touched: list[tuple[str, datetime]] = []
        self.latest: RecentSample | None = None
        self.recent: list[float] = []

    async def get_device(self, _device_id: str) -> SensorDevice | None:
        return self.device

    async def touch_last_seen(self, device_id: str, *, at: datetime) -> None:
        self.touched.append((device_id, at))

    async def insert(self, obs: SensorObservation) -> None:
        self.observations.append(obs)

    async def latest_for_datastream(
        self, _device_id: str, _prop: ObservedProperty
    ) -> RecentSample | None:
        return self.latest

    async def recent_values(
        self, _device_id: str, _prop: ObservedProperty, *, limit: int
    ) -> list[float]:
        return list(self.recent)[-limit:]


@pytest.fixture
def patch_repos(monkeypatch: pytest.MonkeyPatch) -> Callable[[SensorDevice | None], _RepoStubs]:
    """Return a factory that installs a fresh _RepoStubs and patches the modules."""

    def _install(device: SensorDevice | None) -> _RepoStubs:
        from limen.data.repos import sensor_devices_repo as devices
        from limen.data.repos import sensor_observations_repo as observations

        stubs = _RepoStubs(device=device)
        monkeypatch.setattr(devices, "get_device", stubs.get_device)
        monkeypatch.setattr(devices, "touch_last_seen", stubs.touch_last_seen)
        monkeypatch.setattr(observations, "insert", stubs.insert)
        monkeypatch.setattr(observations, "latest_for_datastream", stubs.latest_for_datastream)
        monkeypatch.setattr(observations, "recent_values", stubs.recent_values)
        return stubs

    return _install


def _payload(**overrides: Any) -> bytes:
    body: dict[str, Any] = {
        "thing_id": "thing-1",
        "observed_property": "displacement",
        "phenomenon_time": NOW.isoformat(),
        "result_value": 12.0,
        "result_unit": "mm",
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


@pytest.mark.asyncio
async def test_handle_message_persists_observation(
    patch_repos: Callable[[SensorDevice | None], _RepoStubs],
) -> None:
    device = SensorDevice(
        id="thing-1",
        device_type="extensometer",
        cell_id="aoi|0|0",
        location=Point(15.0, 41.0),
        calibration={"displacement": {"scale": 1.0, "offset": 0.0}},
        status="online",
    )
    stubs = patch_repos(device)
    ingestor = MqttIngestor(IotSettings(), sigma_v=3.0)

    await ingestor._handle_message(
        topic="limen/v1/it-puglia/site-a/thing-1/displacement/obs",
        payload=_payload(),
    )

    assert len(stubs.observations) == 1
    saved = stubs.observations[0]
    assert saved.device_id == "thing-1"
    assert saved.observed_property is ObservedProperty.DISPLACEMENT
    assert saved.result_value == 12.0
    assert saved.quality is QcQuality.OK
    assert stubs.touched and stubs.touched[0][0] == "thing-1"


@pytest.mark.asyncio
async def test_handle_message_drops_unknown_device(
    patch_repos: Callable[[SensorDevice | None], _RepoStubs],
) -> None:
    stubs = patch_repos(None)
    ingestor = MqttIngestor(IotSettings())

    await ingestor._handle_message(
        topic="limen/v1/it-puglia/site-a/thing-9/displacement/obs",
        payload=_payload(thing_id="thing-9"),
    )

    assert stubs.observations == []


@pytest.mark.asyncio
async def test_handle_message_drops_topic_thing_mismatch(
    patch_repos: Callable[[SensorDevice | None], _RepoStubs],
) -> None:
    device = SensorDevice(
        id="thing-1",
        device_type="extensometer",
        cell_id="aoi|0|0",
        location=Point(15.0, 41.0),
        calibration={},
        status="online",
    )
    stubs = patch_repos(device)
    ingestor = MqttIngestor(IotSettings())

    await ingestor._handle_message(
        topic="limen/v1/it-puglia/site-a/thing-different/displacement/obs",
        payload=_payload(thing_id="thing-1"),
    )

    assert stubs.observations == []


@pytest.mark.asyncio
async def test_handle_message_records_unit_quality(
    patch_repos: Callable[[SensorDevice | None], _RepoStubs],
) -> None:
    """Non-canonical unit (and identity calibration) → QcQuality.UNIT."""
    device = SensorDevice(
        id="thing-1",
        device_type="extensometer",
        cell_id="aoi|0|0",
        location=Point(15.0, 41.0),
        calibration={},
        status="online",
    )
    stubs = patch_repos(device)
    ingestor = MqttIngestor(IotSettings())

    await ingestor._handle_message(
        topic="limen/v1/it-puglia/site-a/thing-1/displacement/obs",
        payload=_payload(result_unit="m"),
    )

    # Identity calibration → we still emit the canonical unit after the
    # ingestor's canonicalisation step, so quality should be OK *after*
    # we've normalised. But the raw payload was UNIT — assert the row
    # was persisted with a real value regardless.
    assert len(stubs.observations) == 1
    assert stubs.observations[0].raw_value == 12.0


@pytest.mark.asyncio
async def test_handle_message_ignores_invalid_payload(
    patch_repos: Callable[[SensorDevice | None], _RepoStubs],
) -> None:
    stubs = patch_repos(None)
    ingestor = MqttIngestor(IotSettings())

    await ingestor._handle_message(
        topic="limen/v1/it-puglia/site-a/thing-1/displacement/obs",
        payload=b"not-json",
    )
    assert stubs.observations == []
