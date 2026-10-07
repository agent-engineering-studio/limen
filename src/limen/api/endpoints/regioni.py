"""Le regioni da monitorare (#155): numeri, allerta ufficiale e spiegazione."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response

from limen.data.repos import regioni_repo

router = APIRouter(tags=["regioni"])


@router.get("/api/regioni")
async def regioni_da_monitorare(response: Response) -> dict[str, Any]:
    """Le venti regioni dalla più da guardare, con la spiegazione dell'AI.

    L'ordine lo decidono i numeri; la spiegazione accanto è scritta dall'AI
    per (regione, pericolo) e non ne cambia nessuno.
    """
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"regioni": await regioni_repo.monitoraggio()}


@router.get("/api/regioni/rapporto.pdf")
async def rapporto_regioni_pdf(aoi: str | None = None) -> Response:
    """Il rapporto delle regioni in PDF; con ``aoi``, di una regione sola."""
    from limen.report.regioni_pdf import rapporto_pdf

    regioni = await regioni_repo.monitoraggio()
    if aoi is not None:
        regioni = [r for r in regioni if r["aoi_id"] == aoi]
        if not regioni:
            raise HTTPException(status_code=404, detail=f"regione sconosciuta: {aoi}")
    adesso = datetime.now(UTC)
    nome = f"limen-{aoi.removeprefix('it-') if aoi else 'regioni'}-{adesso:%Y%m%d-%H%M}.pdf"
    return Response(
        content=rapporto_pdf(regioni, generato=adesso),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            "Cache-Control": "no-store",
        },
    )
