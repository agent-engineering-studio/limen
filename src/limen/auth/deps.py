"""FastAPI auth dependencies + session-cookie helpers.

``current_user`` resolves the session cookie to a user (or None).
``require_session`` gates protected routes; ``require_role`` gates by role
(admin implies every role — see :meth:`AuthUser.has_role`). Enforcement is only
active when ``AUTH__ENABLED``; otherwise the public/dev API stays open.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from limen.auth import repo
from limen.auth.models import AuthUser
from limen.auth.tokens import session_id
from limen.config.settings import AuthSettings, Settings, get_settings

# Defined locally (not imported from limen.api.dependencies) to avoid a circular
# import: api → main → endpoints.auth → auth.deps. get_settings is the same
# lru_cached singleton the app's SettingsDep ultimately resolves.
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def current_user(request: Request, settings: SettingsDep) -> AuthUser | None:
    token = request.cookies.get(settings.auth.session_cookie_name)
    if not token:
        return None
    return await repo.session_user(session_id(token))


CurrentUser = Annotated[AuthUser | None, Depends(current_user)]


async def require_session(request: Request, settings: SettingsDep) -> AuthUser:
    user = await current_user(request, settings)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="autenticazione richiesta"
        )
    return user


RequireUser = Annotated[AuthUser, Depends(require_session)]


def require_role(role: str) -> Callable[..., Awaitable[AuthUser]]:
    async def _dep(request: Request, settings: SettingsDep) -> AuthUser:
        user = await require_session(request, settings)
        if not user.has_role(role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permesso negato")
        return user

    return _dep


def set_session_cookie(response: Response, token: str, settings: AuthSettings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(key=settings.session_cookie_name, path="/")
