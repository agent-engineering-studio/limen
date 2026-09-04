"""Comune risk lookup — leaderboard + detail (read-only over mv_comune_risk).

**Landslide only.** ``mv_comune_risk`` is pinned to the default hazard in SQL
(migration 028) because its ``exposure_rank`` reads a component key that only
the landslide breakdown has. These endpoints therefore accept ``hazard`` and
**refuse** anything else rather than silently returning landslide numbers
under another label — FastAPI would otherwise drop an unknown query param and
the client would never know. The multi-hazard comune rollup is #58 (Fase 4).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from limen.api.schemas import ComuneDetailResponse, ComuneListResponse, ComuneRisk
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.repos import comune_risk

router = APIRouter(tags=["comuni"])


def _require_default_hazard(hazard: HazardType) -> None:
    if hazard is not DEFAULT_HAZARD:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"il rollup comunale è disponibile solo per {DEFAULT_HAZARD.value}: "
                f"la vista è fissata su quel pericolo"
            ),
        )


@router.get("/api/comuni", response_model=ComuneListResponse)
async def list_comuni(
    aoi: str | None = None,
    limit: int = 50,
    hazard: HazardType = DEFAULT_HAZARD,
) -> ComuneListResponse:
    _require_default_hazard(hazard)
    rows = await comune_risk.top_comuni(aoi_id=aoi, limit=limit)
    return ComuneListResponse(comuni=[ComuneRisk(**r) for r in rows])


@router.get("/api/comune/{istat_code}", response_model=ComuneDetailResponse)
async def get_comune(istat_code: str, hazard: HazardType = DEFAULT_HAZARD) -> ComuneDetailResponse:
    _require_default_hazard(hazard)
    detail = await comune_risk.comune_detail(istat_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="comune non trovato")
    return ComuneDetailResponse(comune=ComuneRisk(**detail["comune"]), cells=detail["cells"])
