"""SMTP email channel using ``aiosmtplib``.

Multipart message: a plain-text fallback ``+`` an HTML body. The
recipient list is set at construction time from
:class:`EmailChannelSettings` so an operator can dispatch to a
distribution group without modifying code.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import aiosmtplib

from limen.config.settings import EmailChannelSettings
from limen.core.logging import get_logger
from limen.notifications.base import AlertPayload, NotificationChannel

log = get_logger(__name__)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    aiosmtplib.SMTPException,
    smtplib.SMTPException,
    OSError,
    TimeoutError,
)


def _render_text(payload: AlertPayload) -> str:
    lines = [
        f"Limen — allerta {payload.max_level.value}",
        f"AOI: {payload.aoi_id}",
        f"Picco: {payload.max_score:.2f}",
        "",
        payload.summary_it,
    ]
    if payload.cells:
        lines.append("")
        lines.append("Celle ad alta priorità:")
        for c in payload.cells[:10]:
            lines.append(
                f"  - {c.cell_id} ({c.level.value}, {c.score:.2f}, priorità {c.priority:.2f})"
            )
    if payload.map_url:
        lines.append("")
        lines.append(f"Mappa: {payload.map_url}")
    lines.append("")
    lines.append(f"-- modello {payload.pipeline_version}")
    return "\n".join(lines)


def _render_html(payload: AlertPayload) -> str:
    rows = []
    for c in payload.cells[:10]:
        link = (
            f'<a href="{c.map_url}">{c.cell_id}</a>' if c.map_url else f"<code>{c.cell_id}</code>"
        )
        rows.append(
            f"<tr><td>{link}</td><td>{c.level.value}</td>"
            f"<td>{c.score:.2f}</td><td>{c.priority:.2f}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>Cella</th><th>Livello</th>"
        "<th>Score</th><th>Priorità</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )
    map_para = f'<p>🗺 <a href="{payload.map_url}">Apri la mappa</a></p>' if payload.map_url else ""
    return (
        f"<h2>Limen — allerta {payload.max_level.value}</h2>"
        f"<p>AOI <code>{payload.aoi_id}</code> · "
        f"picco <strong>{payload.max_score:.2f}</strong></p>"
        f"<p>{payload.summary_it}</p>"
        f"{table}"
        f"{map_para}"
        f"<p><small>modello {payload.pipeline_version}</small></p>"
    )


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, settings: EmailChannelSettings) -> None:
        self._settings = settings

    @property
    def is_enabled(self) -> bool:
        return bool(
            self._settings.smtp_host and self._settings.from_address and self._settings.recipients
        )

    async def send(self, payload: AlertPayload) -> bool:
        if not self.is_enabled:
            log.debug("email.skip", reason="missing host / from / recipients")
            return False

        msg = EmailMessage()
        msg["Subject"] = (
            f"[Limen] Allerta {payload.max_level.value} — "
            f"{payload.aoi_id} ({payload.max_score:.2f})"
        )
        assert self._settings.from_address is not None
        msg["From"] = self._settings.from_address
        msg["To"] = ", ".join(self._settings.recipients)
        msg.set_content(_render_text(payload))
        msg.add_alternative(_render_html(payload), subtype="html")

        password = (
            self._settings.password.get_secret_value()
            if self._settings.password is not None
            else None
        )

        try:
            await aiosmtplib.send(
                msg,
                hostname=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.username,
                password=password,
                start_tls=self._settings.use_starttls,
                use_tls=self._settings.use_tls,
                timeout=self._settings.timeout_seconds,
            )
        except _DEGRADATION_EXC as exc:
            log.warning(
                "email.send.degraded",
                error=str(exc),
                error_type=type(exc).__name__,
                host=self._settings.smtp_host,
            )
            return False

        log.info(
            "email.send",
            host=self._settings.smtp_host,
            recipients=len(self._settings.recipients),
        )
        return True


__all__ = ["EmailChannel"]
