"""I contributi degli esperti dall'ispettore della cella: partono per mail, non si salvano."""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from limen.api.dependencies import DepsDep
from limen.core import contributi
from limen.notifications.email import invia_testo

router = APIRouter(tags=["contributi"])


class ContributoRisposta(BaseModel):
    ricevuto: bool


@router.post(
    "/api/contributi",
    response_model=ContributoRisposta,
    status_code=status.HTTP_201_CREATED,
)
async def invia_contributo(
    dati: contributi.ContributoIn, request: Request, deps: DepsDep
) -> ContributoRisposta:
    """Manda il contributo a chi cura il progetto; risponde solo dopo la mail."""
    s = deps.settings
    # `X-Real-IP` lo scrive nginx con l'indirizzo vero; `X-Forwarded-For` no,
    # perché il proxy aggiunge in coda a quello che il client manda, e uvicorn
    # ne prende il primo: un programma potrebbe cambiare indirizzo a ogni invio.
    ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client else "sconosciuto"
    )
    try:
        esito = await contributi.ricevi(
            dati,
            ip=ip,
            settings=s.contributi,
            map_base_url=s.alert.map_base_url,
            invia=partial(invia_testo, s.notifications.email),
        )
    except contributi.CellaSconosciutaError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"cella sconosciuta: {exc}"
        ) from None
    if isinstance(esito, contributi.TroppiInvii):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="troppi contributi in poco tempo: riprova fra un'ora",
        )
    if isinstance(esito, contributi.NonPartito):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="il contributo non è partito: riprova fra qualche minuto",
        )
    return ContributoRisposta(ricevuto=True)
