"""Generic webhook channel — POST the alert JSON to an agent gateway.

Built for the OpenClaw ``/hooks`` endpoint (bearer token, JSON body) but
deliberately agnostic: any HTTP receiver works. The URL is config, so
the gateway can live on localhost today and on a dedicated VPS
tomorrow — no code change, just ``NOTIFICATIONS__WEBHOOK__URL``.
"""

from __future__ import annotations

import httpx
from tenacity import RetryError

from limen.config.settings import WebhookChannelSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.notifications.base import AlertPayload, NotificationChannel

log = get_logger(__name__)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    RetryError,
    TimeoutError,
    OSError,
)


class WebhookChannel(NotificationChannel):
    name = "webhook"

    def __init__(self, settings: WebhookChannelSettings) -> None:
        self._settings = settings

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.url)

    async def send(self, payload: AlertPayload) -> bool:
        if not self.is_enabled:
            log.debug("webhook.skip", reason="url missing")
            return False
        assert self._settings.url is not None  # narrow for mypy
        headers: dict[str, str] = {}
        if self._settings.token is not None:
            headers["Authorization"] = f"Bearer {self._settings.token.get_secret_value()}"
        # `text` top-level: OpenClaw /hooks/wake requires it ("message" on
        # /hooks/agent — see docs/openclaw.md). Generic receivers read the
        # full alert from `payload`.
        body = {
            "text": payload.summary_it,
            "message": payload.summary_it,
            "payload": payload.model_dump(mode="json"),
        }
        client = await SharedHttpClient.get()
        try:
            resp = await fetch_with_retry(
                "POST",
                self._settings.url,
                client=client,
                json=body,
                headers=headers or None,
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "webhook.send.degraded",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False

        log.info("webhook.send", status=resp.status_code, url=self._settings.url)
        return resp.status_code < 400


__all__ = ["WebhookChannel"]
