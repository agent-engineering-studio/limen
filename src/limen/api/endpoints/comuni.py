"""Rischio per comune — classifica e dettaglio, su tutti i pericoli.

**Non è più a pericolo unico.** `mv_comune_risk` era fissata sulle frane in
SQL (migrazione 028) e questi endpoint rifiutavano qualunque altro pericolo:
scegliendo «Alluvione» metà colonna della dashboard continuava a parlare
d'altro, e la domanda che un tecnico comunale fa davvero — «il mio comune,
per tutti i pericoli» — non aveva una superficie che la rispondesse.

Dalla migrazione 051 ogni riga porta i tre pericoli affiancati. Il parametro
`hazard` resta accettato e **ordina** la classifica su quel pericolo invece
di filtrarla: la riga mostra comunque tutti e tre, perché un comune non
smette di poter bruciare mentre si guardano le frane.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from limen.api.schemas import ComuneDetailResponse, ComuneListResponse, ComuneRisk
from limen.data.repos import comune_risk

router = APIRouter(tags=["comuni"])


@router.get("/api/comuni", response_model=ComuneListResponse)
async def list_comuni(
    aoi: str | None = None,
    limit: int = 50,
    q: str | None = Query(
        None,
        description="Cerca per nome. Con una ricerca la soglia non si applica: "
        "chi cerca il proprio comune vuole vederlo anche quando è tranquillo.",
        max_length=64,
    ),
) -> ComuneListResponse:
    rows = await comune_risk.top_comuni(aoi_id=aoi, limit=limit, query=q)
    return ComuneListResponse(comuni=[ComuneRisk(**r) for r in rows])


@router.get("/api/comune/{istat_code}", response_model=ComuneDetailResponse)
async def get_comune(istat_code: str) -> ComuneDetailResponse:
    detail = await comune_risk.comune_detail(istat_code)
    if detail is None:
        raise HTTPException(status_code=404, detail="comune non trovato")
    return ComuneDetailResponse(comune=ComuneRisk(**detail["comune"]), cells=detail["cells"])
