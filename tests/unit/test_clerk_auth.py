"""Clerk JWT dependency: disabled → open; enabled → requires a bearer token."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request

from limen.api.auth import require_user
from limen.config.settings import Settings


def _settings(**overrides: object) -> Settings:
    return cast(Settings, cast(Any, Settings)(_env_file=None, **overrides))


def _request(headers: dict[str, str]) -> Request:
    # require_user only touches request.headers.get(...) — a dict suffices.
    return cast(Request, cast(Any, type("Req", (), {"headers": headers})()))


def test_auth_disabled_is_open() -> None:
    out = asyncio.run(require_user(_request({}), _settings()))
    assert out == {}


def test_auth_enabled_missing_token_401() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_user(_request({}), _settings(clerk={"enabled": True})))
    assert exc.value.status_code == 401


def test_auth_enabled_bad_token_401() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            require_user(
                _request({"Authorization": "Bearer not.a.jwt"}),
                _settings(
                    clerk={"enabled": True, "jwks_url": "https://example.test/.well-known/jwks.json"}
                ),
            )
        )
    assert exc.value.status_code == 401
