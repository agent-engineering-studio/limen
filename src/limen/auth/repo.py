"""Auth persistence — asyncpg queries over users / auth_codes / sessions.

Boundary layer: returns ``AuthUser`` DTOs or raw rows, no business rules. Uses
the shared pool via :func:`limen.data.db.acquire` (same pattern as the MCP /
A2A read tools).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from limen.auth.models import AuthUser, PublicUser
from limen.data.db import acquire

_USER_COLS = "id, email, first_name, last_name, password_hash, email_verified, status, roles"


def _to_user(row: Any) -> AuthUser:
    return AuthUser(
        id=str(row["id"]),
        email=str(row["email"]),
        first_name=row["first_name"],
        last_name=row["last_name"],
        email_verified=row["email_verified"],
        status=row["status"],
        roles=list(row["roles"]),
        has_password=row["password_hash"] is not None,
    )


async def create_user(
    *,
    email: str,
    first_name: str,
    last_name: str,
    password_hash: str | None,
    roles: list[str],
    email_verified: bool = False,
) -> AuthUser:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO users (email, first_name, last_name, password_hash, roles, email_verified)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING {_USER_COLS}
            """,
            email,
            first_name,
            last_name,
            password_hash,
            roles,
            email_verified,
        )
    return _to_user(row)


async def get_by_email(email: str) -> AuthUser | None:
    async with acquire() as conn:
        row = await conn.fetchrow(f"SELECT {_USER_COLS} FROM users WHERE email = $1", email)
    return _to_user(row) if row else None


async def get_credentials(email: str) -> tuple[AuthUser | None, str | None]:
    """User + stored password hash in one query (login path only)."""
    async with acquire() as conn:
        row = await conn.fetchrow(f"SELECT {_USER_COLS} FROM users WHERE email = $1", email)
    if row is None:
        return None, None
    return _to_user(row), row["password_hash"]


async def get_by_id(user_id: str) -> AuthUser | None:
    async with acquire() as conn:
        row = await conn.fetchrow(f"SELECT {_USER_COLS} FROM users WHERE id = $1::uuid", user_id)
    return _to_user(row) if row else None


async def set_email_verified(user_id: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET email_verified = true, updated_at = now() WHERE id = $1::uuid",
            user_id,
        )


async def set_password(user_id: str, password_hash: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET password_hash = $2, updated_at = now() WHERE id = $1::uuid",
            user_id,
            password_hash,
        )


async def update_user(user_id: str, *, roles: list[str], status: str) -> AuthUser | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE users SET roles = $2, status = $3, updated_at = now()
            WHERE id = $1::uuid
            RETURNING {_USER_COLS}
            """,
            user_id,
            roles,
            status,
        )
    return _to_user(row) if row else None


async def list_users(*, query: str | None, limit: int, offset: int) -> list[PublicUser]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, email, first_name, last_name, email_verified, status, roles, created_at
            FROM users
            WHERE ($1::text IS NULL
                   OR email ILIKE '%' || $1 || '%'
                   OR first_name ILIKE '%' || $1 || '%'
                   OR last_name ILIKE '%' || $1 || '%')
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            query,
            limit,
            offset,
        )
    return [
        PublicUser(
            id=str(r["id"]),
            email=str(r["email"]),
            first_name=r["first_name"],
            last_name=r["last_name"],
            email_verified=r["email_verified"],
            status=r["status"],
            roles=list(r["roles"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


# --- auth codes ---------------------------------------------------------------


async def replace_code(*, user_id: str, code_hash: str, purpose: str, expires_at: datetime) -> None:
    """Invalidate any prior code for (user, purpose) and store the new one."""
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM auth_codes WHERE user_id = $1::uuid AND purpose = $2",
            user_id,
            purpose,
        )
        await conn.execute(
            """
                INSERT INTO auth_codes (user_id, code_hash, purpose, expires_at)
                VALUES ($1::uuid, $2, $3, $4)
                """,
            user_id,
            code_hash,
            purpose,
            expires_at,
        )


async def latest_code(user_id: str, purpose: str) -> Any:
    async with acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, code_hash, expires_at, consumed_at, attempts
            FROM auth_codes
            WHERE user_id = $1::uuid AND purpose = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id,
            purpose,
        )


async def bump_code_attempts(code_id: str) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE auth_codes SET attempts = attempts + 1 WHERE id = $1::uuid", code_id
        )


async def consume_code(code_id: str) -> None:
    async with acquire() as conn:
        await conn.execute("UPDATE auth_codes SET consumed_at = now() WHERE id = $1::uuid", code_id)


# --- sessions -----------------------------------------------------------------


async def create_session(
    *, sid: str, user_id: str, expires_at: datetime, user_agent: str | None, ip: str | None
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sessions (id, user_id, expires_at, user_agent, ip)
            VALUES ($1, $2::uuid, $3, $4, $5::inet)
            """,
            sid,
            user_id,
            expires_at,
            user_agent,
            ip,
        )


async def session_user(sid: str) -> AuthUser | None:
    """Return the active user for a live (unexpired) session, else None."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {", ".join("u." + c for c in _USER_COLS.split(", "))}
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = $1 AND s.expires_at > now() AND u.status = 'active'
            """,
            sid,
        )
        if row is not None:
            await conn.execute("UPDATE sessions SET last_seen_at = now() WHERE id = $1", sid)
    return _to_user(row) if row else None


async def delete_session(sid: str) -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = $1", sid)


async def delete_user_sessions(user_id: str) -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE user_id = $1::uuid", user_id)
