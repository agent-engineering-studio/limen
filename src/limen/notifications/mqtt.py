"""MQTT publisher channel using ``aiomqtt``.

V1 opens a fresh connection per dispatch — alerts are rare (minutes
apart at most), so the simplicity of "connect → publish → disconnect"
is worth more than keeping a long-lived session alive. V2+ can
introduce a connection pool if/when alert frequency grows.
"""

from __future__ import annotations

import json

import aiomqtt

from limen.config.settings import MqttChannelSettings
from limen.core.logging import get_logger
from limen.notifications.base import AlertPayload, NotificationChannel

log = get_logger(__name__)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    aiomqtt.MqttError,
    OSError,
    TimeoutError,
)


def _payload_to_json(payload: AlertPayload) -> bytes:
    return json.dumps(payload.model_dump(mode="json"), default=str).encode("utf-8")


class MqttChannel(NotificationChannel):
    name = "mqtt"

    def __init__(self, settings: MqttChannelSettings) -> None:
        self._settings = settings

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.broker_host and self._settings.topic)

    async def send(self, payload: AlertPayload) -> bool:
        if not self.is_enabled:
            log.debug("mqtt.skip", reason="broker_host missing")
            return False
        assert self._settings.broker_host is not None  # narrowed by is_enabled

        body = _payload_to_json(payload)
        password = (
            self._settings.password.get_secret_value()
            if self._settings.password is not None
            else None
        )

        try:
            async with aiomqtt.Client(
                hostname=self._settings.broker_host,
                port=self._settings.broker_port,
                username=self._settings.username,
                password=password,
                identifier=self._settings.client_id,
                tls_params=aiomqtt.TLSParameters() if self._settings.tls else None,
            ) as client:
                await client.publish(
                    topic=self._settings.topic,
                    payload=body,
                    qos=self._settings.qos,
                )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "mqtt.send.degraded",
                error=str(exc),
                error_type=type(exc).__name__,
                broker=self._settings.broker_host,
            )
            return False

        log.info(
            "mqtt.send",
            topic=self._settings.topic,
            qos=self._settings.qos,
            bytes=len(body),
        )
        return True


__all__ = ["MqttChannel"]
