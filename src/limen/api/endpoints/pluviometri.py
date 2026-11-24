"""La pioggia dei pluviometri regionali, sempre per una zona franosa.

Le stesse due domande degli strumenti MCP ``landslide_zone_rain`` e
``rain_before_landslides``: nessuna pioggia per coordinata, solo per una cella
o per le celle franose di un comune. La logica sta in
:mod:`limen.core.pioggia_frane`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response

from limen.api.dependencies import DepsDep
from limen.core.pioggia_frane import pioggia_prima_delle_frane, pioggia_zona_franosa

router = APIRouter(prefix="/api/pluviometri", tags=["pluviometri"])


def _zona(cell_id: str | None, istat_code: str | None) -> None:
    if (cell_id is None) == (istat_code is None):
        raise HTTPException(status_code=422, detail="indica cell_id oppure istat_code")


@router.get("/zona")
async def zona(
    response: Response,
    deps: DepsDep,
    cell_id: str | None = None,
    istat_code: str | None = None,
    ore: int = Query(72, ge=1, le=720),
    fino_a: datetime | None = None,
) -> dict[str, Any]:
    """I pluviometri vicini alla zona franosa: cumulate e evento contro la soglia d'innesco."""
    _zona(cell_id, istat_code)
    response.headers["Cache-Control"] = "public, max-age=900"
    return await pioggia_zona_franosa(
        cell_id=cell_id,
        istat_code=istat_code,
        ore=ore,
        fino_a=fino_a,
        raggio_km=deps.settings.pluviometri.raggio_km,
    )


@router.get("/frane")
async def frane(
    response: Response,
    deps: DepsDep,
    dal: datetime,
    cell_id: str | None = None,
    istat_code: str | None = None,
    al: datetime | None = None,
    ore_prima: int = Query(72, ge=1, le=720),
) -> dict[str, Any]:
    """Le frane datate della zona e la pioggia misurata nelle ore prima di ognuna."""
    _zona(cell_id, istat_code)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return await pioggia_prima_delle_frane(
        cell_id=cell_id,
        istat_code=istat_code,
        dal=dal,
        al=al,
        ore_prima=ore_prima,
        raggio_km=deps.settings.pluviometri.raggio_km,
    )
