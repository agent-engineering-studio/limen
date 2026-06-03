"""Vector-tile redirect to pg_tileserv.

The frontend (Phase 6) will consume these tiles directly from
pg_tileserv. Phase 5 only exposes a thin redirect so the SPA's tile
URLs don't need to know the pg_tileserv hostname.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from limen.api.dependencies import DepsDep

router = APIRouter(prefix="/api/tiles", tags=["tiles"])


@router.get("/{layer}/{z}/{x}/{y}.pbf")
async def tile_redirect(
    layer: str,
    z: int,
    x: int,
    y: int,
    deps: DepsDep,
) -> Response:
    """Redirect the tile request to the configured ``pg_tileserv`` instance."""
    base = deps.settings.api.pg_tileserv_url
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pg_tileserv URL is not configured (set API__PG_TILESERV_URL)",
        )
    url = f"{base.rstrip('/')}/{layer}/{z}/{x}/{y}.pbf"
    return RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
