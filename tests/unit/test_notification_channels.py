"""Per-channel unit tests with respx / mocking — no live network."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from limen.config.settings import (
    EmailChannelSettings,
    MqttChannelSettings,
    TelegramChannelSettings,
)
from limen.core.models.risk import RiskLevel
from limen.integrations._http import SharedHttpClient
from limen.notifications.base import AlertedCell, AlertPayload
from limen.notifications.email import EmailChannel
from limen.notifications.mqtt import MqttChannel
from limen.notifications.telegram import TelegramChannel


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
                map_url="http://map.test/?cell=aoi%7C0%7C0",
            )
        ],
        summary_it="Allerta di test in italiano.",
        map_url="http://map.test/?aoi=it-puglia",
        pipeline_version="v1-deterministic",
        dispatched_at=datetime(2026, 6, 1, 12, 30, tzinfo=UTC),
    )


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
async def test_telegram_disabled_without_token() -> None:
    channel = TelegramChannel(TelegramChannelSettings())
    assert channel.is_enabled is False
    assert await channel.send(_payload()) is False


async def test_telegram_send_success() -> None:
    settings = TelegramChannelSettings(
        bot_token=SecretStr("dummy"),
        chat_id="@limen-alerts",
        api_base_url="http://api.telegram.test",
    )
    with respx.mock() as mock:
        route = mock.post("http://api.telegram.test/botdummy/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True, "result": {}})
        )
        ok = await TelegramChannel(settings).send(_payload())
    assert ok is True
    assert route.call_count == 1
    body = route.calls[0].request.read().decode()
    assert "@limen-alerts" in body
    assert "Allerta" in body


async def test_telegram_5xx_returns_false_without_raising() -> None:
    settings = TelegramChannelSettings(
        bot_token=SecretStr("dummy"),
        chat_id="@limen-alerts",
        api_base_url="http://api.telegram.test",
    )
    with respx.mock() as mock:
        mock.post("http://api.telegram.test/botdummy/sendMessage").mock(
            return_value=httpx.Response(503)
        )
        ok = await TelegramChannel(settings).send(_payload())
    assert ok is False


# ---------------------------------------------------------------------------
# MQTT — mock aiomqtt.Client
# ---------------------------------------------------------------------------
class _FakeMqttClient:
    """Minimal async context manager that mimics aiomqtt.Client."""

    last_publish: dict[str, object] | None = None
    should_raise: bool = False

    def __init__(self, *args: object, **kwargs: object) -> None:
        _FakeMqttClient.last_init = (args, kwargs)

    async def __aenter__(self) -> _FakeMqttClient:
        if _FakeMqttClient.should_raise:
            import aiomqtt

            raise aiomqtt.MqttError("connect failed")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def publish(self, *, topic: str, payload: bytes, qos: int) -> None:
        _FakeMqttClient.last_publish = {
            "topic": topic,
            "payload": payload,
            "qos": qos,
        }


async def test_mqtt_disabled_without_broker_host() -> None:
    channel = MqttChannel(MqttChannelSettings())
    assert channel.is_enabled is False
    assert await channel.send(_payload()) is False


async def test_mqtt_publish_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.notifications.mqtt as mqtt_mod

    _FakeMqttClient.last_publish = None
    _FakeMqttClient.should_raise = False
    monkeypatch.setattr(mqtt_mod.aiomqtt, "Client", _FakeMqttClient)
    settings = MqttChannelSettings(
        broker_host="mosquitto.test",
        broker_port=1883,
        topic="limen/alerts",
        qos=1,
    )
    ok = await MqttChannel(settings).send(_payload())
    assert ok is True
    assert _FakeMqttClient.last_publish is not None
    assert _FakeMqttClient.last_publish["topic"] == "limen/alerts"
    assert _FakeMqttClient.last_publish["qos"] == 1
    # Payload is JSON bytes; smoke-check it parses + carries the AOI.
    import json

    body = json.loads(_FakeMqttClient.last_publish["payload"].decode())  # type: ignore[arg-type]
    assert body["aoi_id"] == "it-puglia"


async def test_mqtt_connect_failure_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.notifications.mqtt as mqtt_mod

    _FakeMqttClient.should_raise = True
    monkeypatch.setattr(mqtt_mod.aiomqtt, "Client", _FakeMqttClient)
    settings = MqttChannelSettings(broker_host="mosquitto.test")
    ok = await MqttChannel(settings).send(_payload())
    assert ok is False


# ---------------------------------------------------------------------------
# Email — mock aiosmtplib.send
# ---------------------------------------------------------------------------
async def test_email_disabled_without_recipients() -> None:
    channel = EmailChannel(EmailChannelSettings())
    assert channel.is_enabled is False
    assert await channel.send(_payload()) is False


async def test_email_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    async def fake_send(msg, **kwargs):  # type: ignore[no-untyped-def]
        calls.append((msg, kwargs))
        return ({}, "OK")

    import limen.notifications.email as email_mod

    monkeypatch.setattr(email_mod.aiosmtplib, "send", fake_send)

    settings = EmailChannelSettings(
        smtp_host="smtp.test",
        from_address="alerts@test",
        recipients=["ops@test", "second@test"],
    )
    ok = await EmailChannel(settings).send(_payload())
    assert ok is True
    assert len(calls) == 1
    msg, kwargs = calls[0]
    assert kwargs["hostname"] == "smtp.test"
    assert kwargs["port"] == 587
    assert msg["To"] == "ops@test, second@test"
    text_body = msg.get_body(("plain",)).get_content()
    assert "Allerta" in text_body
    assert "it-puglia" in text_body


async def test_email_send_failure_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_send(msg, **kwargs):  # type: ignore[no-untyped-def, ARG001]
        import aiosmtplib

        raise aiosmtplib.SMTPException("relay refused")

    import limen.notifications.email as email_mod

    monkeypatch.setattr(email_mod.aiosmtplib, "send", fake_send)

    settings = EmailChannelSettings(
        smtp_host="smtp.test",
        from_address="alerts@test",
        recipients=["ops@test"],
    )
    ok = await EmailChannel(settings).send(_payload())
    assert ok is False
