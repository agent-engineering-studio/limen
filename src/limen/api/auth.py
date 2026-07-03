"""Clerk JWT validation for protected FastAPI endpoints.

Off unless ``CLERK__ENABLED`` — the public, read-only map endpoints stay open
and dev/test need no Clerk config. When enabled, protected endpoints require a
Bearer Clerk **session JWT**, verified against the instance JWKS (public RSA
keys). The Clerk secret key is never used here.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKClient

from limen.api.dependencies import SettingsDep
from limen.config.settings import Settings
from limen.core.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    # Cached per URL — PyJWKClient keeps its own signing-key cache across calls.
    return PyJWKClient(jwks_url)


def _verify(token: str, settings: Settings) -> dict[str, Any]:
    clerk = settings.clerk
    if not clerk.jwks_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Clerk auth enabled but CLERK__JWKS_URL is unset",
        )
    try:
        signing_key = _jwks_client(clerk.jwks_url).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=clerk.issuer,
            options={"verify_aud": False, "require": ["exp", "iat"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        log.warning("clerk.jwt.invalid", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid Clerk token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if clerk.authorized_parties and claims.get("azp") not in clerk.authorized_parties:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized party")
    return claims


async def require_user(request: Request, settings: SettingsDep) -> dict[str, Any]:
    """Require a valid Clerk JWT on protected endpoints.

    No-op (returns ``{}``) when Clerk auth is disabled, so the public map and
    dev/test keep working without any Clerk configuration.
    """
    if not settings.clerk.enabled:
        return {}
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _verify(header.removeprefix("Bearer "), settings)


RequireUser = Annotated[dict[str, Any], Depends(require_user)]
