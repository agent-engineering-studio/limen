"""HTTP endpoint groups.

Each module contributes an :class:`fastapi.APIRouter` aggregated in
:func:`limen.api.endpoints.all_routers`.
"""

from collections.abc import Iterable

from fastapi import APIRouter

from limen.api.endpoints import alerts, aoi, health, monitor, risk, tiles


def all_routers() -> Iterable[APIRouter]:
    return (
        health.router,
        aoi.router,
        monitor.router,
        risk.router,
        alerts.router,
        tiles.router,
    )


__all__ = ["all_routers"]
