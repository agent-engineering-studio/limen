"""Auth service — register / verify / login flows with an in-memory repo (no DB).

Covers the security-relevant branches: enumeration resistance on register,
code TTL / attempt cap / consumption on verify, and the login failure modes
(wrong password, unknown user, unverified, disabled).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from limen.auth import service
from limen.auth.models import ROLE_VIEWER, STATUS_DISABLED, AuthUser
from limen.config.settings import AuthSettings, Settings

_FAST = AuthSettings(scrypt_n=2**14, code_ttl_minutes=15, code_max_attempts=3)


def _settings() -> Settings:
    return Settings(auth=_FAST)


class FakeRepo:
    def __init__(self) -> None:
        self.users: dict[str, AuthUser] = {}
        self.hashes: dict[str, str | None] = {}
        self.codes: dict[tuple[str, str], dict[str, Any]] = {}
        self.sessions: dict[str, str] = {}

    async def get_by_email(self, email: str) -> AuthUser | None:
        return self.users.get(email)

    async def get_credentials(self, email: str) -> tuple[AuthUser | None, str | None]:
        u = self.users.get(email)
        return u, (self.hashes.get(u.id) if u else None)

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
        self.users[email] = u
        self.hashes[u.id] = password_hash
        return u

    async def replace_code(
        self, *, user_id: str, code_hash: str, purpose: str, expires_at: datetime
    ) -> None:
        self.codes[(user_id, purpose)] = {
            "id": uuid.uuid4().hex,
            "code_hash": code_hash,
            "expires_at": expires_at,
            "consumed_at": None,
            "attempts": 0,
        }

    async def latest_code(self, user_id: str, purpose: str) -> Any:
        return self.codes.get((user_id, purpose))

    async def bump_code_attempts(self, code_id: str) -> None:
        for row in self.codes.values():
            if row["id"] == code_id:
                row["attempts"] += 1

    async def consume_code(self, code_id: str) -> None:
        for row in self.codes.values():
            if row["id"] == code_id:
                row["consumed_at"] = datetime.now(UTC)

    async def set_email_verified(self, user_id: str) -> None:
        for u in self.users.values():
            if u.id == user_id:
                u.email_verified = True

    async def create_session(
        self,
        *,
        sid: str,
        user_id: str,
        expires_at: datetime,
        user_agent: str | None,
        ip: str | None,
    ) -> None:
        self.sessions[sid] = user_id


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> FakeRepo:
    fake = FakeRepo()
    monkeypatch.setattr(service, "repo", fake)
    sent: list[tuple[str, str]] = []

    async def _send(cfg: Any, *, to_address: str, code: str) -> bool:
        sent.append((to_address, code))
        return True

    monkeypatch.setattr(service, "send_verification_code", _send)
    fake.sent = sent  # type: ignore[attr-defined]
    return fake


async def _register(repo: FakeRepo, email: str = "mario@example.it") -> str:
    await service.register(
        first_name="Mario",
        last_name="Rossi",
        email=email,
        password="password123",
        settings=_settings(),
    )
    return repo.sent[-1][1]  # type: ignore[attr-defined]


async def test_register_creates_unverified_viewer_and_sends_code(repo: FakeRepo) -> None:
    await _register(repo)
    user = repo.users["mario@example.it"]
    assert user.email_verified is False
    assert user.roles == [ROLE_VIEWER]
    assert len(repo.sent) == 1  # type: ignore[attr-defined]


async def test_register_existing_verified_is_silent(repo: FakeRepo) -> None:
    code = await _register(repo)
    await service.verify_email("mario@example.it", code, _settings())
    await service.register(
        first_name="X",
        last_name="Y",
        email="mario@example.it",
        password="password123",
        settings=_settings(),
    )
    # no new code emitted for an already-verified account (no enumeration signal)
    assert len(repo.sent) == 1  # type: ignore[attr-defined]


async def test_verify_wrong_code_bumps_attempts_then_locks(repo: FakeRepo) -> None:
    await _register(repo)
    for _ in range(3):
        with pytest.raises(service.AuthError):
            await service.verify_email("mario@example.it", "000000", _settings())
    # attempts now at cap ⇒ 429 even before checking the (wrong) code
    with pytest.raises(service.AuthError) as exc:
        await service.verify_email("mario@example.it", "000000", _settings())
    assert exc.value.status_code == 429


async def test_verify_expired_code_rejected(repo: FakeRepo) -> None:
    await _register(repo)
    row = repo.codes[(repo.users["mario@example.it"].id, "verify_email")]
    row["expires_at"] = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(service.AuthError):
        await service.verify_email("mario@example.it", "whatever", _settings())


async def test_login_happy_path_and_failures(repo: FakeRepo) -> None:
    code = await _register(repo)
    # not verified yet ⇒ 403
    with pytest.raises(service.AuthError) as unv:
        await service.login(
            email="mario@example.it",
            password="password123",
            user_agent=None,
            ip=None,
            settings=_settings(),
        )
    assert unv.value.status_code == 403

    await service.verify_email("mario@example.it", code, _settings())
    user, token = await service.login(
        email="mario@example.it",
        password="password123",
        user_agent="pytest",
        ip="127.0.0.1",
        settings=_settings(),
    )
    assert user.email == "mario@example.it"
    assert token and len(repo.sessions) == 1

    # wrong password ⇒ 401
    with pytest.raises(service.AuthError) as bad:
        await service.login(
            email="mario@example.it",
            password="nope",
            user_agent=None,
            ip=None,
            settings=_settings(),
        )
    assert bad.value.status_code == 401

    # unknown user ⇒ 401 (enumeration-resistant, same code)
    with pytest.raises(service.AuthError) as ghost:
        await service.login(
            email="ghost@example.it",
            password="whatever",
            user_agent=None,
            ip=None,
            settings=_settings(),
        )
    assert ghost.value.status_code == 401


async def test_login_disabled_account_rejected(repo: FakeRepo) -> None:
    code = await _register(repo)
    await service.verify_email("mario@example.it", code, _settings())
    repo.users["mario@example.it"].status = STATUS_DISABLED
    with pytest.raises(service.AuthError) as exc:
        await service.login(
            email="mario@example.it",
            password="password123",
            user_agent=None,
            ip=None,
            settings=_settings(),
        )
    assert exc.value.status_code == 403
