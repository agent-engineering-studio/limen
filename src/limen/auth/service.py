"""Auth orchestration — register, verify email, login, logout.

Security posture: generic responses that don't reveal whether an email is
registered (enumeration resistance); constant-time password + code checks with
a dummy hash on the no-user path to equalise timing; codes are short-lived with
an attempt cap. Business rules live here; persistence is in :mod:`repo`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache

from limen.auth import repo
from limen.auth.email import send_verification_code
from limen.auth.models import (
    PURPOSE_VERIFY_EMAIL,
    ROLE_VIEWER,
    STATUS_DISABLED,
    VALID_ROLES,
    AuthUser,
    PublicUser,
)
from limen.auth.passwords import hash_password, verify_password
from limen.auth.tokens import generate_code, hash_code, new_session_token, session_id, verify_code
from limen.config.settings import Settings
from limen.core.logging import get_logger

log = get_logger(__name__)


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@lru_cache(maxsize=4)
def _dummy_hash(n: int, r: int, p: int) -> str:
    # Precomputed once per work-factor: burned on the no-user login path so a
    # missing account costs the same wall time as a real one.
    from limen.config.settings import AuthSettings

    return hash_password(
        "dummy-password-for-timing", AuthSettings(scrypt_n=n, scrypt_r=r, scrypt_p=p)
    )


async def _issue_code(user_id: str, email: str, settings: Settings) -> None:
    code = generate_code(settings.auth.code_length)
    expires = datetime.now(UTC) + timedelta(minutes=settings.auth.code_ttl_minutes)
    await repo.replace_code(
        user_id=user_id, code_hash=hash_code(code), purpose=PURPOSE_VERIFY_EMAIL, expires_at=expires
    )
    await send_verification_code(settings.notifications.email, to_address=email, code=code)


async def register(
    *, first_name: str, last_name: str, email: str, password: str, settings: Settings
) -> None:
    """Create an unverified account and email a code. Enumeration-resistant."""
    if not settings.auth.registration_open:
        raise AuthError(403, "la registrazione pubblica è disabilitata")
    existing = await repo.get_by_email(email)
    if existing is not None:
        # Don't reveal the account exists. If it's still unverified, re-send a
        # code so a lost first email isn't a dead end; otherwise do nothing.
        if not existing.email_verified:
            await _issue_code(existing.id, email, settings)
        else:
            log.info("auth.register.existing_verified", email=email)
        return
    user = await repo.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password, settings.auth),
        roles=[ROLE_VIEWER],
    )
    await _issue_code(user.id, email, settings)
    log.info("auth.register.created", user_id=user.id)


async def resend_code(email: str, settings: Settings) -> None:
    user = await repo.get_by_email(email)
    if user is not None and not user.email_verified:
        await _issue_code(user.id, email, settings)


async def verify_email(email: str, code: str, settings: Settings) -> None:
    user = await repo.get_by_email(email)
    generic = AuthError(400, "codice non valido o scaduto")
    if user is None:
        raise generic
    if user.email_verified:
        return
    row = await repo.latest_code(user.id, PURPOSE_VERIFY_EMAIL)
    if row is None or row["consumed_at"] is not None:
        raise generic
    if row["attempts"] >= settings.auth.code_max_attempts:
        raise AuthError(429, "troppi tentativi, richiedi un nuovo codice")
    if row["expires_at"] <= datetime.now(UTC):
        raise generic
    if not verify_code(code, row["code_hash"]):
        await repo.bump_code_attempts(str(row["id"]))
        raise generic
    await repo.consume_code(str(row["id"]))
    await repo.set_email_verified(user.id)
    log.info("auth.verify.ok", user_id=user.id)


async def login(
    *, email: str, password: str, user_agent: str | None, ip: str | None, settings: Settings
) -> tuple[AuthUser, str]:
    user, password_hash = await repo.get_credentials(email)
    invalid = AuthError(401, "credenziali non valide")
    if user is None or password_hash is None:
        # Equalise timing with the real-user path, then fail generically.
        auth = settings.auth
        verify_password(password, _dummy_hash(auth.scrypt_n, auth.scrypt_r, auth.scrypt_p))
        raise invalid
    if not verify_password(password, password_hash):
        raise invalid
    if not user.email_verified:
        raise AuthError(403, "email non ancora verificata")
    if not user.is_active:
        raise AuthError(403, "account disabilitato")
    token = new_session_token()
    expires = datetime.now(UTC) + timedelta(hours=settings.auth.session_ttl_hours)
    await repo.create_session(
        sid=session_id(token), user_id=user.id, expires_at=expires, user_agent=user_agent, ip=ip
    )
    log.info("auth.login.ok", user_id=user.id)
    return user, token


async def create_session_for(
    user: AuthUser, *, user_agent: str | None, ip: str | None, settings: Settings
) -> str:
    """Mint a session for an already-authenticated user (password or SPID)."""
    token = new_session_token()
    expires = datetime.now(UTC) + timedelta(hours=settings.auth.session_ttl_hours)
    await repo.create_session(
        sid=session_id(token), user_id=user.id, expires_at=expires, user_agent=user_agent, ip=ip
    )
    return token


async def spid_complete(
    *, code: str, user_agent: str | None, ip: str | None, settings: Settings
) -> tuple[AuthUser, str]:
    """Finish the SPID OIDC flow: exchange code → provision user → session."""
    from limen.auth import spid

    claims = await spid.exchange_code(settings.spid, code=code)
    user = await spid.provision_user(claims)
    if not user.is_active:
        raise AuthError(403, "account disabilitato")
    token = await create_session_for(user, user_agent=user_agent, ip=ip, settings=settings)
    log.info("auth.spid.login", user_id=user.id)
    return user, token


async def logout(token: str) -> None:
    await repo.delete_session(session_id(token))


# --- admin (require_role("admin")) -------------------------------------------


def _validate_roles(roles: list[str]) -> None:
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise AuthError(400, f"ruoli non validi: {', '.join(invalid)}")


def _to_public(user: AuthUser) -> PublicUser:
    return PublicUser(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        email_verified=user.email_verified,
        status=user.status,
        roles=user.roles,
    )


async def admin_list_users(*, query: str | None, limit: int, offset: int) -> list[PublicUser]:
    return await repo.list_users(query=query, limit=max(1, min(limit, 200)), offset=max(0, offset))


async def admin_create_user(
    *,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
    roles: list[str],
    settings: Settings,
) -> PublicUser:
    _validate_roles(roles)
    if await repo.get_by_email(email) is not None:
        raise AuthError(409, "esiste già un utente con questa email")
    user = await repo.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password_hash=hash_password(password, settings.auth),
        roles=roles,
        email_verified=True,  # admin-created accounts skip email verification
    )
    log.info("auth.admin.created", user_id=user.id, roles=roles)
    return _to_public(user)


async def admin_update_user(*, user_id: str, roles: list[str], status: str) -> PublicUser:
    _validate_roles(roles)
    updated = await repo.update_user(user_id, roles=roles, status=status)
    if updated is None:
        raise AuthError(404, "utente non trovato")
    if status == STATUS_DISABLED:
        # Disabling takes effect immediately — drop the user's live sessions.
        await repo.delete_user_sessions(user_id)
    log.info("auth.admin.updated", user_id=user_id, roles=roles, status=status)
    return _to_public(updated)
