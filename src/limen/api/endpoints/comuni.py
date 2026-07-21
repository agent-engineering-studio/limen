"""Comune risk lookup — leaderboard + detail (read-only over mv_comune_risk)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from limen.api.schemas import ComuneDetailResponse, ComuneListResponse, ComuneRisk
from limen.data.repos import comune_risk

router = APIRouter(tags=["comuni"])


@router.get("/api/comuni", response_model=ComuneListResponse)
async def list_comuni(aoi: str | None = None, limit: int = 50) -> ComuneListResponse:
    rows = await comune_risk.top_comuni(aoi_id=aoi, limit=limit)
    return ComuneListResponse(comuni=[ComuneRisk(**r) for r in rows])


@router.get("/api/comune/{istat_code}", response_model=ComuneDetailResponse)
async def get_comune(istat_code: str) -> ComuneDetailResponse:
    detail = await comune_risk.comune_detail(istat_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="comune non trovato")
    return ComuneDetailResponse(comune=ComuneRisk(**detail["comune"]), cells=detail["cells"])
