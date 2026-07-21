"""Admin user-management endpoints — admin role only.

List / create / update users and their roles. The whole router is gated by
``require_role("admin")``; business rules (role validation, session revocation
on disable) live in :mod:`limen.auth.service`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from limen.auth import service
from limen.auth.deps import SettingsDep, require_role
from limen.auth.models import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    PublicUser,
    UserListResponse,
)

# Module-level so tests can target it via dependency_overrides (require_role
# returns a fresh closure each call, which wouldn't match otherwise).
require_admin = require_role("admin")

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/users", response_model=UserListResponse)
async def list_users(
    query: str | None = None, limit: int = 100, offset: int = 0
) -> UserListResponse:
    users = await service.admin_list_users(query=query, limit=limit, offset=offset)
    return UserListResponse(users=users)


@router.post("/users", response_model=PublicUser, status_code=201)
async def create_user(body: AdminCreateUserRequest, settings: SettingsDep) -> PublicUser:
    return await service.admin_create_user(
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        password=body.password,
        roles=body.roles,
        settings=settings,
    )


@router.patch("/users/{user_id}", response_model=PublicUser)
async def update_user(user_id: str, body: AdminUpdateUserRequest) -> PublicUser:
    return await service.admin_update_user(user_id=user_id, roles=body.roles, status=body.status)
