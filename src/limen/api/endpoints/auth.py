"""Auth endpoints — register, verify email, login/logout, me.

Thin: request validation is in the DTOs, business rules in
:mod:`limen.auth.service`. Register / resend return a generic message
regardless of whether the email exists (enumeration resistance). Login sets an
httpOnly session cookie; the browser never sees a token in JS.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from limen.auth import service
from limen.auth.deps import (
    RequireUser,
    SettingsDep,
    clear_session_cookie,
    set_session_cookie,
)
from limen.auth.models import (
    AuthUser,
    LoginRequest,
    MeResponse,
    PublicUser,
    RegisterRequest,
    ResendCodeRequest,
    VerifyEmailRequest,
)
from limen.auth.spid import SpidError, build_authorization_url
from limen.auth.tokens import new_session_token

router = APIRouter(prefix="/api/auth", tags=["auth"])

_GENERIC = {"message": "Se l'indirizzo è valido, riceverai un codice di verifica via email."}


def _public(user: AuthUser) -> PublicUser:
    return PublicUser(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        email_verified=user.email_verified,
        status=user.status,
        roles=user.roles,
    )


async def auth_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    err = exc if isinstance(exc, service.AuthError) else service.AuthError(500, "errore")
    return JSONResponse(status_code=err.status_code, content={"detail": err.detail})


@router.post("/register")
async def register(body: RegisterRequest, settings: SettingsDep) -> dict[str, str]:
    await service.register(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password=body.password,
        settings=settings,
    )
    return _GENERIC


@router.post("/resend-code")
async def resend_code(body: ResendCodeRequest, settings: SettingsDep) -> dict[str, str]:
    await service.resend_code(body.email, settings)
    return _GENERIC


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest, settings: SettingsDep) -> dict[str, str]:
    await service.verify_email(body.email, body.code, settings)
    return {"message": "Email verificata. Ora puoi accedere."}


@router.post("/login", response_model=MeResponse)
async def login(
    body: LoginRequest, request: Request, response: Response, settings: SettingsDep
) -> MeResponse:
    user, token = await service.login(
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
        settings=settings,
    )
    set_session_cookie(response, token, settings.auth)
    return MeResponse(user=_public(user))


@router.post("/logout")
async def logout(request: Request, response: Response, settings: SettingsDep) -> dict[str, str]:
    token = request.cookies.get(settings.auth.session_cookie_name)
    if token:
        await service.logout(token)
    clear_session_cookie(response, settings.auth)
    return {"message": "Sessione terminata."}


@router.get("/me", response_model=MeResponse)
async def me(user: RequireUser) -> MeResponse:
    return MeResponse(user=_public(user))


_SPID_STATE_COOKIE = "limen_spid_state"


@router.get("/config")
async def auth_config(settings: SettingsDep) -> dict[str, bool]:
    """Public: which login providers are available (for the SPA to render)."""
    return {"spid_enabled": settings.spid.configured}


@router.get("/spid/login")
async def spid_login(settings: SettingsDep) -> Response:
    if not settings.spid.configured:
        raise service.AuthError(404, "SPID non configurato")
    state = new_session_token()
    url = build_authorization_url(settings.spid, state=state, nonce=new_session_token())
    resp = RedirectResponse(url, status_code=307)
    resp.set_cookie(
        _SPID_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=settings.auth.cookie_secure,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/spid/callback")
async def spid_callback(request: Request, code: str, state: str, settings: SettingsDep) -> Response:
    if not settings.spid.configured:
        raise service.AuthError(404, "SPID non configurato")
    expected = request.cookies.get(_SPID_STATE_COOKIE)
    if not expected or expected != state:
        raise service.AuthError(400, "state SPID non valido")
    try:
        _user, token = await service.spid_complete(
            code=code,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
            settings=settings,
        )
    except SpidError as exc:
        raise service.AuthError(502, f"login SPID fallito: {exc}") from exc
    resp = RedirectResponse(settings.spid.post_login_url, status_code=303)
    set_session_cookie(resp, token, settings.auth)
    resp.delete_cookie(_SPID_STATE_COOKIE, path="/")
    return resp
