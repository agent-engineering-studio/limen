"""SPID / CIE login via OIDC — seam (fase D).

Standard OIDC authorization-code flow so it can be pointed at an AgID-accredited
SPID/CIE OIDC proxy/aggregator when accreditation lands. Everything is gated by
``settings.spid.configured``; unconfigured ⇒ the flow fails closed. Provisioning
links the SPID subject to an existing account (by subject, then by email) or
creates a new pre-verified one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from limen.auth import repo
from limen.auth.models import ROLE_VIEWER, AuthUser
from limen.config.settings import SpidSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)


class SpidError(Exception):
    """SPID flow failure (config missing, token exchange failed, bad claims)."""


@dataclass(frozen=True)
class SpidClaims:
    subject: str
    first_name: str
    last_name: str
    email: str


def build_authorization_url(cfg: SpidSettings, *, state: str, nonce: str) -> str:
    if not cfg.configured or cfg.authorization_endpoint is None:
        raise SpidError("SPID non configurato")
    params = {
        "response_type": "code",
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "scope": " ".join(cfg.scopes),
        "state": state,
        "nonce": nonce,
    }
    return f"{cfg.authorization_endpoint}?{urlencode(params)}"


def _claims_from_userinfo(data: dict[str, Any]) -> SpidClaims:
    # SPID/CIE expose given_name/family_name/email; fall back to OIDC 'name'.
    subject = str(data.get("sub") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    first = str(data.get("given_name") or data.get("name") or "").strip()
    last = str(data.get("family_name") or "").strip()
    if not subject or not email:
        raise SpidError("claims SPID incompleti (sub/email mancanti)")
    return SpidClaims(
        subject=subject, first_name=first or "SPID", last_name=last or "Utente", email=email
    )


async def exchange_code(cfg: SpidSettings, *, code: str) -> SpidClaims:
    """Exchange the auth code for tokens, then read userinfo → claims."""
    if not cfg.configured or cfg.token_endpoint is None or cfg.userinfo_endpoint is None:
        raise SpidError("SPID non configurato")
    assert cfg.client_secret is not None
    client = await SharedHttpClient.get()
    try:
        token_resp = await fetch_with_retry(
            "POST",
            cfg.token_endpoint,
            client=client,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg.redirect_uri,
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret.get_secret_value(),
            },
        )
        access_token = token_resp.json().get("access_token")
        if not access_token:
            raise SpidError("token endpoint non ha restituito access_token")
        userinfo = await fetch_with_retry(
            "GET",
            cfg.userinfo_endpoint,
            client=client,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except SpidError:
        raise
    except Exception as exc:  # transport / HTTP / JSON — surface as SPID failure
        raise SpidError(f"scambio OIDC fallito: {exc}") from exc
    return _claims_from_userinfo(userinfo.json())


async def provision_user(claims: SpidClaims) -> AuthUser:
    """Link the SPID subject to an account (by subject, then email) or create it."""
    existing = await repo.get_by_spid_subject(claims.subject)
    if existing is not None:
        return existing
    by_email = await repo.get_by_email(claims.email)
    if by_email is not None:
        await repo.link_spid_subject(by_email.id, claims.subject)
        log.info("auth.spid.linked", user_id=by_email.id)
        return by_email
    created = await repo.create_user(
        email=claims.email,
        first_name=claims.first_name,
        last_name=claims.last_name,
        password_hash=None,  # SPID-only account (no local password)
        roles=[ROLE_VIEWER],
        email_verified=True,  # identity verified by SPID
        spid_subject=claims.subject,
    )
    log.info("auth.spid.created", user_id=created.id)
    return created
