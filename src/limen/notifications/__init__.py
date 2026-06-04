"""Multi-channel alert notifications (Strategy pattern).

Public surface:

* :class:`NotificationChannel` — Protocol every channel implements.
* :class:`AlertPayload` — channel-agnostic message DTO.
* :func:`build_alert_payload` — build a payload from an
  :class:`AggregateAssessment` + the dispatch settings.
* :class:`NotificationDispatcher` — runs the configured channels in
  parallel with per-channel exception isolation.
* :func:`build_default_dispatcher` — factory that wires
  :class:`TelegramChannel`, :class:`MqttChannel` and
  :class:`EmailChannel` based on ``NotificationsSettings``.

V1 channels: Telegram, MQTT, Email. Each is enabled independently and
**fails gracefully**: a channel error never propagates to the
workflow.
"""

from limen.notifications.base import (
    AlertPayload,
    NotificationChannel,
    build_alert_payload,
)
from limen.notifications.dispatcher import (
    NotificationDispatcher,
    build_default_dispatcher,
)
from limen.notifications.email import EmailChannel
from limen.notifications.mqtt import MqttChannel
from limen.notifications.telegram import TelegramChannel

__all__ = [
    "AlertPayload",
    "EmailChannel",
    "MqttChannel",
    "NotificationChannel",
    "NotificationDispatcher",
    "TelegramChannel",
    "build_alert_payload",
    "build_default_dispatcher",
]
