"""Auth HTTP layer — cookie on login, /me gating, validation, error mapping.

No DB: the service is stubbed (its logic is covered in test_auth_service.py) and
the session dependency is overridden. This pins the endpoint wiring: cookie set,
401 without a session, 422 on a bad body, AuthError → status code.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import auth as auth_ep
from limen.auth.deps import require_session
from limen.auth.models import AuthUser
from limen.auth.service import AuthError

_USER = AuthUser(
    id="u1",
    email="admin@limen.test",
    first_name="Ada",
    last_name="Root",
    email_verified=True,
    status="active",
    roles=["admin"],
    has_password=True,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _login(**kwargs: object) -> tuple[AuthUser, str]:
        if kwargs.get("password") != "right":
            raise AuthError(401, "credenziali non valide")
        return _USER, "session-token-abc"

    async def _register(**kwargs: object) -> None:
        return None

    monkeypatch.setattr(auth_ep.service, "login", _login)
    monkeypatch.setattr(auth_ep.service, "register", _register)

    app = FastAPI()
    app.include_router(auth_ep.router)
    app.add_exception_handler(AuthError, auth_ep.auth_error_handler)
    return TestClient(app)


def test_login_sets_session_cookie_and_returns_user(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"email": "admin@limen.test", "password": "right"})
    assert resp.status_code == 200
    assert resp.json()["user"]["roles"] == ["admin"]
    assert "limen_session" in resp.cookies
    cookie_header = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie_header


def test_login_wrong_password_maps_to_401(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"email": "admin@limen.test", "password": "nope"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "credenziali non valide"


def test_register_returns_generic_message(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register",
        json={
            "first_name": "Mario",
            "last_name": "Rossi",
            "email": "mario@x.it",
            "password": "password123",
        },
    )
    assert resp.status_code == 200
    assert "riceverai" in resp.json()["message"]


def test_register_rejects_short_password(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/register",
        json={"first_name": "A", "last_name": "B", "email": "x@y.it", "password": "short"},
    )
    assert resp.status_code == 422


def test_me_requires_session(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401

    async def _fake_user() -> AuthUser:
        return _USER

    client.app.dependency_overrides[require_session] = _fake_user
    try:
        resp = client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "admin@limen.test"
    finally:
        client.app.dependency_overrides.clear()
