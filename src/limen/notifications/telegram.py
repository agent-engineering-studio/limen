"""Telegram bot channel.

Implementation note: we call the Bot API directly with the project's
shared :mod:`limen.integrations._http` client (tenacity retry + shared
httpx) rather than pulling in ``python-telegram-bot``. The send-only
surface we need is one POST to ``/bot{token}/sendMessage`` — adding a
full bot-framework dependency would only inflate the runtime image
without buying anything for one-way alerts.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import RetryError

from limen.config.settings import TelegramChannelSettings
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


def _render_html(payload: AlertPayload) -> str:
    """Compose the HTML body. Telegram supports a tag subset only."""
    lines: list[str] = [
        f"<b>⚠ Limen — allerta {payload.max_level.value}</b>",
        f"AOI <code>{payload.aoi_id}</code> · picco <code>{payload.max_score:.2f}</code>",
        "",
        payload.summary_it,
    ]
    if payload.cells:
        lines.append("")
        lines.append("<b>Celle ad alta priorità</b>:")
        for cell in payload.cells[:5]:
            if cell.map_url:
                lines.append(
                    f'• <a href="{cell.map_url}">{cell.cell_id}</a> '
                    f"— {cell.level.value} ({cell.score:.2f})"
                )
            else:
                lines.append(
                    f"• <code>{cell.cell_id}</code> — {cell.level.value} ({cell.score:.2f})"
                )
    if payload.map_url:
        lines.append("")
        lines.append(f'🗺 <a href="{payload.map_url}">Apri la mappa</a>')
    lines.append("")
    lines.append(f"<i>modello {payload.pipeline_version}</i>")
    return "\n".join(lines)


class TelegramChannel(NotificationChannel):
    name = "telegram"

    def __init__(self, settings: TelegramChannelSettings) -> None:
        self._settings = settings

    @property
    def is_enabled(self) -> bool:
        return bool(self._settings.bot_token and self._settings.chat_id)

    async def send(self, payload: AlertPayload) -> bool:
        if not self.is_enabled:
            log.debug("telegram.skip", reason="bot_token or chat_id missing")
            return False
        assert self._settings.bot_token is not None  # narrow for mypy
        token = self._settings.bot_token.get_secret_value()
        url = f"{self._settings.api_base_url.rstrip('/')}/bot{token}/sendMessage"
        body: dict[str, Any] = {
            "chat_id": self._settings.chat_id,
            "text": _render_html(payload),
            "parse_mode": self._settings.parse_mode,
            "disable_web_page_preview": self._settings.disable_web_page_preview,
        }
        client = await SharedHttpClient.get()
        try:
            resp = await fetch_with_retry("POST", url, client=client, json=body)
        except _DEGRADATION_EXC as exc:
            log.warning(
                "telegram.send.degraded",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return False

        ok = bool(resp.json().get("ok", False)) if resp.content else False
        log.info(
            "telegram.send",
            status=resp.status_code,
            ok=ok,
            chat_id=self._settings.chat_id,
        )
        return ok and resp.status_code < 400


__all__ = ["TelegramChannel"]
