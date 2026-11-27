"""Le attivazioni Copernicus EMS in catalogo e il loro registro per comune (#713).

Acqua **osservata dopo** l'evento, da satellite: non è un'allerta né una
previsione di Limen. Ogni risposta porta l'attribuzione della licenza CEMS
(nel CSV, una colonna su ogni riga). La logica sta in
:mod:`limen.core.ems_registro`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response

from limen.core import ems_registro

router = APIRouter(prefix="/api/ems", tags=["ems"])

_CACHE = "public, max-age=3600"


@router.get("/attivazioni")
async def attivazioni(response: Response) -> dict[str, Any]:
    """Le attivazioni alluvionali Copernicus EMS in ``flood_events``."""
    response.headers["Cache-Control"] = _CACHE
    return {"avvertenza": ems_registro.AVVERTENZA, "attivazioni": await ems_registro.attivazioni()}


@router.get("/attivazioni/{codice}/comuni", response_model=None)
async def comuni(
    codice: str, response: Response, formato: Literal["json", "csv"] = "json"
) -> dict[str, Any] | Response:
    """I comuni ISTAT toccati dall'acqua osservata, con i km² per comune."""
    codice = codice.upper()
    righe = await ems_registro.registro(codice)
    if righe is None:
        raise HTTPException(status_code=404, detail="attivazione non in catalogo")
    if formato == "csv":
        return Response(
            content=ems_registro.registro_csv(codice, righe),
            media_type="text/csv; charset=utf-8",
            headers={
                "Cache-Control": _CACHE,
                "Content-Disposition": f'attachment; filename="{codice}_comuni.csv"',
            },
        )
    response.headers["Cache-Control"] = _CACHE
    return ems_registro.registro_json(codice, righe)
