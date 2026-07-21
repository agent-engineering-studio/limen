"""SPID OIDC seam — pure helpers, provisioning (fake repo), fail-closed gating."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import auth as auth_ep
from limen.auth import spid
from limen.auth.models import ROLE_VIEWER, AuthUser
from limen.auth.spid import SpidClaims, SpidError, _claims_from_userinfo, build_authorization_url
from limen.config.settings import SpidSettings

_CFG = SpidSettings(
    client_id="cid",
    client_secret="secret",  # type: ignore[arg-type]
    authorization_endpoint="https://idp.example/authorize",
    token_endpoint="https://idp.example/token",
    userinfo_endpoint="https://idp.example/userinfo",
    redirect_uri="https://limen.example/api/auth/spid/callback",
)


def test_configured_flag() -> None:
    assert _CFG.configured is True
    assert SpidSettings().configured is False


def test_authorization_url_has_oidc_params() -> None:
    url = build_authorization_url(_CFG, state="st8", nonce="n1")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["state"] == ["st8"]
    assert q["redirect_uri"] == [_CFG.redirect_uri]


def test_authorization_url_fails_closed_when_unconfigured() -> None:
    with pytest.raises(SpidError):
        build_authorization_url(SpidSettings(), state="s", nonce="n")


def test_claims_mapping_and_incomplete() -> None:
    c = _claims_from_userinfo(
        {"sub": "TINIT-XYZ", "email": "M@X.IT", "given_name": "Mario", "family_name": "Rossi"}
    )
    assert c == SpidClaims("TINIT-XYZ", "Mario", "Rossi", "m@x.it")
    with pytest.raises(SpidError):
        _claims_from_userinfo({"sub": "x"})  # no email


class _Repo:
    def __init__(self) -> None:
        self.by_sub: dict[str, AuthUser] = {}
        self.by_email: dict[str, AuthUser] = {}
        self.linked: list[tuple[str, str]] = []

    async def get_by_spid_subject(self, subject: str) -> AuthUser | None:
        return self.by_sub.get(subject)

    async def get_by_email(self, email: str) -> AuthUser | None:
        return self.by_email.get(email)

    async def link_spid_subject(self, user_id: str, subject: str) -> None:
        self.linked.append((user_id, subject))

    async def create_user(self, **kw: Any) -> AuthUser:
        u = AuthUser(
            id=uuid.uuid4().hex,
            email=kw["email"],
            first_name=kw["first_name"],
            last_name=kw["last_name"],
            email_verified=kw["email_verified"],
            status="active",
            roles=kw["roles"],
            has_password=kw["password_hash"] is not None,
        )
        return u


async def test_provision_links_by_email_then_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _Repo()
    monkeypatch.setattr(spid, "repo", repo)
    claims = SpidClaims("TINIT-1", "Mario", "Rossi", "m@x.it")

    # 1) new subject + new email ⇒ create SPID-only, pre-verified, viewer
    created = await spid.provision_user(claims)
    assert created.has_password is False
    assert created.email_verified is True
    assert created.roles == [ROLE_VIEWER]

    # 2) existing email, new subject ⇒ link (no duplicate)
    repo.by_email["m@x.it"] = created
    linked = await spid.provision_user(claims)
    assert linked.id == created.id
    assert repo.linked == [(created.id, "TINIT-1")]

    # 3) known subject ⇒ returned directly
    repo.by_sub["TINIT-1"] = created
    assert (await spid.provision_user(claims)).id == created.id


def test_endpoints_fail_closed_when_spid_unconfigured() -> None:
    # Default settings ⇒ SPID off: /config reports false, /spid/login 404.
    from limen.auth.service import AuthError

    app = FastAPI()
    app.include_router(auth_ep.router)
    app.add_exception_handler(AuthError, auth_ep.auth_error_handler)
    client = TestClient(app)
    assert client.get("/api/auth/config").json() == {"spid_enabled": False}
    assert client.get("/api/auth/spid/login").status_code == 404
