"""Il radar DPC per la mappa (#643): i temporali di adesso, dal database.

Li scrive la sveglia radar del worker; qui si leggono soltanto, così una pagina
pubblica non diventa richieste al servizio del DPC, che ha un tetto dichiarato
(#627).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Response

from limen.api.dependencies import DepsDep
from limen.api.schemas import TemporaleOut, TemporaliResponse
from limen.data.repos import radar_temporali_repo
from limen.integrations.dpc.temporali import geojson

router = APIRouter(prefix="/api/radar", tags=["radar"])


@router.get("/temporali", response_model=TemporaliResponse)
async def temporali(response: Response, deps: DepsDep) -> TemporaliResponse:
    """I temporali dell'ultimo fotogramma SRI e dove vanno; lista vuota se non piove forte
    o se la sveglia non legge il radar da più di due giri."""
    response.headers["Cache-Control"] = "public, max-age=60"
    righe = await radar_temporali_repo.leggi(_eta_massima(deps))
    return TemporaliResponse(
        osservato_at=righe[0].osservato_at if righe else None,
        temporali=[TemporaleOut(**asdict(t)) for t in righe],
    )


@router.get("/temporali.geojson")
async def temporali_geojson(response: Response, deps: DepsDep) -> dict[str, Any]:
    """Gli stessi temporali per la mappa: centri e linea fino a dove saranno fra un'ora."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return geojson(await radar_temporali_repo.leggi(_eta_massima(deps)))


def _eta_massima(deps: Any) -> timedelta:
    return timedelta(minutes=2 * deps.settings.nowcast.interval_minutes)
