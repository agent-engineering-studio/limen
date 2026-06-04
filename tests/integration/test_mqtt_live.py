"""Live MQTT integration — :class:`MqttChannel` against a real Mosquitto broker.

Spins up ``eclipse-mosquitto:2.0`` via testcontainers, lets the channel
publish, and subscribes from a second aiomqtt client to verify the
payload arrives intact. Gated on Docker (same fixture machinery as
the Postgres tests).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import aiomqtt
import pytest
from testcontainers.core.container import DockerContainer

from limen.config.settings import MqttChannelSettings
from limen.core.models.risk import RiskLevel
from limen.notifications.base import AlertedCell, AlertPayload
from limen.notifications.mqtt import MqttChannel

pytestmark = pytest.mark.integration


def _payload() -> AlertPayload:
    return AlertPayload(
        aoi_id="it-puglia",
        max_level=RiskLevel.High,
        max_score=0.72,
        cells=[
            AlertedCell(
                cell_id="aoi|0|0",
                score=0.72,
                level=RiskLevel.High,
                priority=1.05,
                map_url=None,
            )
        ],
        summary_it="Allerta di test.",
        map_url=None,
        pipeline_version="v1-deterministic",
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )


@pytest.fixture(scope="module")
async def mosquitto_container() -> AsyncIterator[tuple[str, int]]:
    """Boot Mosquitto with a bind-mounted anonymous-listener config.

    The default 2.x image config binds to localhost only — useless for
    testcontainers' port-forwarding. We override by writing a tiny
    config file to a tempdir and mounting it read-only at the path the
    image already reads on start-up.
    """
    cfg_dir = Path(tempfile.mkdtemp(prefix="limen-mosquitto-"))
    (cfg_dir / "mosquitto.conf").write_text(
        "listener 1883 0.0.0.0\nallow_anonymous true\n",
        encoding="utf-8",
    )
    container = (
        DockerContainer("eclipse-mosquitto:2.0")
        .with_exposed_ports(1883)
        .with_volume_mapping(str(cfg_dir), "/mosquitto/config", "ro")
    )
    container.start()
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(1883))
        # Probe until the broker accepts a connection.
        last_exc: Exception | None = None
        for _ in range(40):
            try:
                async with aiomqtt.Client(hostname=host, port=port):
                    break
            except aiomqtt.MqttError as e:
                last_exc = e
                await asyncio.sleep(0.5)
        else:
            pytest.fail(f"Mosquitto never became reachable: {last_exc}")
        yield host, port
    finally:
        container.stop()


async def test_mqtt_publish_round_trip(
    mosquitto_container: tuple[str, int],
) -> None:
    host, port = mosquitto_container
    topic = "limen/alerts/test"

    settings = MqttChannelSettings(
        broker_host=host,
        broker_port=port,
        topic=topic,
        qos=1,
        client_id="limen-test-publisher",
    )

    # Subscribe in parallel so we can prove the publish lands.
    received: list[bytes] = []

    async def _subscribe() -> None:
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            identifier="limen-test-subscriber",
        ) as client:
            await client.subscribe(topic, qos=1)
            async for message in client.messages:
                received.append(bytes(message.payload))
                return

    sub_task = asyncio.create_task(_subscribe())
    # Tiny delay so the subscribe is registered before we publish.
    await asyncio.sleep(0.5)

    ok = await MqttChannel(settings).send(_payload())
    assert ok is True

    await asyncio.wait_for(sub_task, timeout=5.0)
    assert received, "subscriber never received a message"

    body = json.loads(received[0].decode())
    assert body["aoi_id"] == "it-puglia"
    assert body["max_level"] == "High"
    assert body["cells"][0]["cell_id"] == "aoi|0|0"
