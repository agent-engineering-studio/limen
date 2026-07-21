"""Send a verification code to one address, reusing the SMTP notification config.

Distinct from the ``email`` notification channel (which fans out to a fixed
recipient list): here the recipient is the single user being verified. When
SMTP is unconfigured (dev/test) the code is logged instead of sent, so the flow
is exercisable without a mail server — never in production, where SMTP is set.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

import aiosmtplib

from limen.config.settings import EmailChannelSettings
from limen.core.logging import get_logger

log = get_logger(__name__)

_DEGRADATION_EXC: tuple[type[BaseException], ...] = (
    aiosmtplib.SMTPException,
    smtplib.SMTPException,
    OSError,
    TimeoutError,
)


def _smtp_ready(cfg: EmailChannelSettings) -> bool:
    return bool(cfg.smtp_host and cfg.from_address)


async def send_verification_code(cfg: EmailChannelSettings, *, to_address: str, code: str) -> bool:
    if not _smtp_ready(cfg):
        # Dev affordance: no SMTP ⇒ surface the code in the logs so the
        # verify flow can be tested. Production always has SMTP configured.
        log.warning("auth.code.no_smtp", to=to_address, code=code)
        return False

    msg = EmailMessage()
    msg["Subject"] = "Limen — codice di verifica"
    assert cfg.from_address is not None
    msg["From"] = cfg.from_address
    msg["To"] = to_address
    msg.set_content(
        f"Il tuo codice di verifica Limen è: {code}\n\n"
        "Inseriscilo nella pagina di conferma per attivare l'account. "
        "Il codice scade a breve. Se non hai richiesto la registrazione, ignora questa email."
    )

    password = cfg.password.get_secret_value() if cfg.password is not None else None
    try:
        await aiosmtplib.send(
            msg,
            hostname=cfg.smtp_host,
            port=cfg.smtp_port,
            username=cfg.username,
            password=password,
            start_tls=cfg.use_starttls,
            use_tls=cfg.use_tls,
            timeout=cfg.timeout_seconds,
        )
    except _DEGRADATION_EXC as exc:
        log.warning("auth.code.send.degraded", error=str(exc), error_type=type(exc).__name__)
        return False
    log.info("auth.code.sent", to=to_address)
    return True
