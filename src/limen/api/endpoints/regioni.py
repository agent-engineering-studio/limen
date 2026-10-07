"""Le regioni da monitorare (#155): numeri, allerta ufficiale e spiegazione."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

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
