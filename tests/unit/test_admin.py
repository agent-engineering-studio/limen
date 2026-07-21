"""Admin user management — service logic (fake repo) + endpoint gating (no DB)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from limen.api.endpoints import admin as admin_ep
from limen.auth import service
from limen.auth.models import STATUS_DISABLED, AuthUser
from limen.auth.service import AuthError
from limen.config.settings import AuthSettings, Settings

_FAST = AuthSettings(scrypt_n=2**14)


class FakeRepo:
    def __init__(self) -> None:
        self.users: dict[str, AuthUser] = {}
        self.by_email: dict[str, AuthUser] = {}
        self.revoked: list[str] = []

    async def get_by_email(self, email: str) -> AuthUser | None:
        return self.by_email.get(email)

    async def create_user(
        self,
        *,
        email: str,
        first_name: str,
        last_name: str,
        password_hash: str | None,
        roles: list[str],
        email_verified: bool = False,
    ) -> AuthUser:
        u = AuthUser(
            id=uuid.uuid4().hex,
            email=email,
            first_name=first_name,
            last_name=last_name,
            email_verified=email_verified,
            status="active",
            roles=roles,
            has_password=password_hash is not None,
        )
        self.users[u.id] = u
        self.by_email[email] = u
        return u

    async def update_user(self, user_id: str, *, roles: list[str], status: str) -> AuthUser | None:
        u = self.users.get(user_id)
        if u is None:
            return None
        u.roles = roles
        u.status = status
        return u

    async def list_users(self, *, query: str | None, limit: int, offset: int) -> list[Any]:
        return list(self.users.values())

    async def delete_user_sessions(self, user_id: str) -> None:
        self.revoked.append(user_id)


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> FakeRepo:
    fake = FakeRepo()
    monkeypatch.setattr(service, "repo", fake)
    return fake


async def test_admin_create_validates_roles_and_dedupes(repo: FakeRepo) -> None:
    with pytest.raises(AuthError) as bad:
        await service.admin_create_user(
            first_name="A",
            last_name="B",
            email="a@b.it",
            password="password123",
            roles=["wizard"],
            settings=Settings(auth=_FAST),
        )
    assert bad.value.status_code == 400  # invalid role

    user = await service.admin_create_user(
        first_name="Ada",
        last_name="Op",
        email="op@limen.test",
        password="password123",
        roles=["operatore"],
        settings=Settings(auth=_FAST),
    )
    assert user.email_verified is True  # admin-created ⇒ pre-verified
    assert user.roles == ["operatore"]

    with pytest.raises(AuthError) as dup:
        await service.admin_create_user(
            first_name="X",
            last_name="Y",
            email="op@limen.test",
            password="password123",
            roles=["viewer"],
            settings=Settings(auth=_FAST),
        )
    assert dup.value.status_code == 409


async def test_admin_update_disable_revokes_sessions(repo: FakeRepo) -> None:
    u = await service.admin_create_user(
        first_name="Ada",
        last_name="Op",
        email="op@limen.test",
        password="password123",
        roles=["operatore"],
        settings=Settings(auth=_FAST),
    )
    updated = await service.admin_update_user(
        user_id=u.id, roles=["operatore", "ml-ops"], status=STATUS_DISABLED
    )
    assert updated.status == STATUS_DISABLED
    assert repo.revoked == [u.id]

    with pytest.raises(AuthError) as missing:
        await service.admin_update_user(user_id="ghost", roles=["viewer"], status="active")
    assert missing.value.status_code == 404


def test_admin_router_requires_a_session() -> None:
    # No session cookie ⇒ the require_admin gate rejects before any handler.
    app = FastAPI()
    app.include_router(admin_ep.router)
    client = TestClient(app)
    assert client.get("/api/admin/users").status_code == 401


def test_admin_router_happy_path_with_override(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = AuthUser(
        id="a1",
        email="admin@limen.test",
        first_name="Ada",
        last_name="Root",
        email_verified=True,
        status="active",
        roles=["admin"],
        has_password=True,
    )

    async def _list(**kwargs: object) -> list[Any]:
        return []

    monkeypatch.setattr(admin_ep.service, "admin_list_users", _list)
    app = FastAPI()
    app.include_router(admin_ep.router)
    app.dependency_overrides[admin_ep.require_admin] = lambda: admin
    client = TestClient(app)
    resp = client.get("/api/admin/users")
    assert resp.status_code == 200
    assert resp.json() == {"users": []}
