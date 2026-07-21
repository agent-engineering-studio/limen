"""``limen create-admin`` — bootstrap or promote an admin account (idempotent).

Reads ``LIMEN_ADMIN_EMAIL`` + ``LIMEN_ADMIN_PASSWORD`` (and optional
``LIMEN_ADMIN_FIRST`` / ``LIMEN_ADMIN_LAST``). Re-runnable: an existing account
is promoted to admin, verified, and its password reset to the given one.
"""

from __future__ import annotations

import os

from limen.auth import repo
from limen.auth.models import ROLE_ADMIN, STATUS_ACTIVE
from limen.auth.passwords import hash_password
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    email = os.environ.get("LIMEN_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("LIMEN_ADMIN_PASSWORD", "")
    first = os.environ.get("LIMEN_ADMIN_FIRST", "Admin").strip() or "Admin"
    last = os.environ.get("LIMEN_ADMIN_LAST", "Limen").strip() or "Limen"
    if not email or not password:
        log.error("cli.create_admin.missing_env", need="LIMEN_ADMIN_EMAIL + LIMEN_ADMIN_PASSWORD")
        return 2

    async with lifespan_pool():
        await run_migrations()
        existing = await repo.get_by_email(email)
        pw_hash = hash_password(password, settings.auth)
        if existing is not None:
            roles = sorted({*existing.roles, ROLE_ADMIN})
            await repo.update_user(existing.id, roles=roles, status=STATUS_ACTIVE)
            await repo.set_password(existing.id, pw_hash)
            await repo.set_email_verified(existing.id)
            log.info("cli.create_admin.promoted", email=email, user_id=existing.id)
        else:
            user = await repo.create_user(
                email=email,
                first_name=first,
                last_name=last,
                password_hash=pw_hash,
                roles=[ROLE_ADMIN],
                email_verified=True,
            )
            log.info("cli.create_admin.created", email=email, user_id=user.id)
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
