"""Auth DTOs + role constants.

Request models validate at the boundary (email normalised, password length).
Roles are a closed set managed by the admin. ``AuthUser`` is the internal
representation built from a DB row; ``PublicUser`` is what the API returns.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

ROLE_ADMIN = "admin"
ROLE_ML_OPS = "ml-ops"
ROLE_OPERATORE = "operatore"
ROLE_VIEWER = "viewer"
VALID_ROLES: frozenset[str] = frozenset({ROLE_ADMIN, ROLE_ML_OPS, ROLE_OPERATORE, ROLE_VIEWER})

# auth_codes.purpose
PURPOSE_VERIFY_EMAIL = "verify_email"

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

_MIN_PASSWORD = 8


def _normalise_email(value: str) -> str:
    v = value.strip().lower()
    if "@" not in v or v.startswith("@") or v.endswith("@"):
        raise ValueError("indirizzo email non valido")
    return v


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=_MIN_PASSWORD, max_length=200)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalise_email(v)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class VerifyEmailRequest(BaseModel):
    email: str
    code: str = Field(min_length=4, max_length=10)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalise_email(v)


class ResendCodeRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalise_email(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalise_email(v)


class AuthUser(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    email_verified: bool
    status: str
    roles: list[str]
    has_password: bool

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    def has_role(self, role: str) -> bool:
        return role in self.roles or ROLE_ADMIN in self.roles


class PublicUser(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    email_verified: bool
    status: str
    roles: list[str]
    created_at: datetime | None = None


class MeResponse(BaseModel):
    user: PublicUser
