"""Run notifications channels in parallel with per-channel exception isolation.

Acceptance criterion §1: a failing channel MUST NOT block the other
channels or the workflow. Each :meth:`NotificationChannel.send` is
wrapped by :func:`_send_safe` — exceptions are logged and converted
into a ``False`` outcome.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from limen.config.settings import NotificationsSettings
from limen.core.logging import get_logger
from limen.notifications.base import AlertPayload, NotificationChannel
from limen.notifications.email import EmailChannel
from limen.notifications.mqtt import MqttChannel
from limen.notifications.telegram import TelegramChannel

log = get_logger(__name__)


async def _send_safe(channel: NotificationChannel, payload: AlertPayload) -> bool:
    """Wrap ``channel.send`` so any exception becomes a logged ``False``."""
    try:
        return await channel.send(payload)
    except Exception as exc:
        log.warning(
            "notifications.channel.error",
            channel=channel.name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return False


class NotificationDispatcher:
    """Parallel fan-out to every configured channel."""

    def __init__(self, channels: Iterable[NotificationChannel]) -> None:
        self._channels: list[NotificationChannel] = list(channels)

    @property
    def channel_names(self) -> list[str]:
        return [c.name for c in self._channels]

    @property
    def enabled_names(self) -> list[str]:
        return [c.name for c in self._channels if c.is_enabled]

    async def dispatch(self, payload: AlertPayload) -> dict[str, bool]:
        """Send ``payload`` to every channel concurrently.

        Returns one ``{channel_name: success}`` entry per channel.
        Disabled channels return ``False`` without an attempt; the
        executor records this fact so observability can distinguish
        "no recipients configured" from "delivery failed".
        """
        if not self._channels:
            log.info("notifications.dispatch.empty", note="no channels configured")
            return {}

        results = await asyncio.gather(*(_send_safe(c, payload) for c in self._channels))
        outcome = {c.name: bool(ok) for c, ok in zip(self._channels, results, strict=True)}
        log.info(
            "notifications.dispatch.done",
            outcomes=outcome,
            enabled=self.enabled_names,
        )
        return outcome


def build_default_dispatcher(
    settings: NotificationsSettings,
) -> NotificationDispatcher:
    """Construct the dispatcher honoring ``enabled_channels``.

    Channels whose credentials are absent are still constructed (so
    that ``is_enabled`` is queryable) but they will short-circuit to
    ``False`` at send time. This keeps the dispatcher introspectable
    in tests without forcing operators to set every credential.
    """
    channels: list[NotificationChannel] = []
    enabled = set(settings.enabled_channels)
    if "telegram" in enabled:
        channels.append(TelegramChannel(settings.telegram))
    if "mqtt" in enabled:
        channels.append(MqttChannel(settings.mqtt))
    if "email" in enabled:
        channels.append(EmailChannel(settings.email))
    log.info(
        "notifications.dispatcher.built",
        enabled=sorted(enabled),
        constructed=[c.name for c in channels],
    )
    return NotificationDispatcher(channels)


__all__ = ["NotificationDispatcher", "build_default_dispatcher"]
