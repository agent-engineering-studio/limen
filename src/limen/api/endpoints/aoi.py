"""AOI listing endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from limen.api.dependencies import DepsDep
from limen.api.schemas import AoiListResponse, AoiSummary
from limen.data.db import acquire

router = APIRouter(prefix="/api/aoi", tags=["aoi"])


@router.get("", response_model=AoiListResponse)
async def list_aois(deps: DepsDep) -> AoiListResponse:  # noqa: ARG001 — DI presence forces lifespan check
    """List every AOI in the database."""
    async with acquire() as conn:
        rows = await conn.fetch("SELECT id, name, kind FROM aoi ORDER BY id")
    items = [AoiSummary(id=r["id"], name=r["name"], kind=r["kind"]) for r in rows]
    return AoiListResponse(items=items)
