"""HTTP endpoint groups.

Each module contributes an :class:`fastapi.APIRouter` aggregated in
:func:`limen.api.endpoints.all_routers`.
"""

from collections.abc import Iterable

from fastapi import APIRouter

from limen.api.endpoints import (
    a2a,
    alerts,
    aoi,
    comuni,
    health,
    risk,
    status,
    tiles,
)


def all_routers() -> Iterable[APIRouter]:
    return (
        health.router,
        aoi.router,
        risk.router,
        alerts.router,
        tiles.router,
        a2a.router,
        comuni.router,
        status.router,
    )


__all__ = ["all_routers"]
