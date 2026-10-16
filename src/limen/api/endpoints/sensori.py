"""Il modulo di registrazione dei sensori (#253): una richiesta e una mail, nessun dispositivo."""

from __future__ import annotations

from functools import partial

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from limen.api.dependencies import DepsDep
from limen.core import sensori_registrazione as reg
from limen.notifications.email import invia_testo

router = APIRouter(tags=["sensori"])


class RegistrazioneStato(BaseModel):
    aperta: bool


class RegistrazioneRisposta(BaseModel):
    ricevuta: bool


@router.get("/api/sensori/registrazione", response_model=RegistrazioneStato)
async def stato_registrazione(deps: DepsDep) -> RegistrazioneStato:
    """Se il modulo accetta richieste: chiuso, la pagina non lo mostra."""
    return RegistrazioneStato(aperta=deps.settings.iot.cittadini.registrazione.aperta)


@router.post(
    "/api/sensori/registrazione",
    response_model=RegistrazioneRisposta,
    status_code=status.HTTP_201_CREATED,
)
async def registra_sensore(
    dati: reg.RichiestaSensoreIn, request: Request, deps: DepsDep
) -> RegistrazioneRisposta:
    """Scrive la richiesta e avvisa chi cura il progetto; risponde dopo la mail."""
    s = deps.settings
    # Come per i contributi: `X-Real-IP` lo scrive nginx, il client no.
    ip = request.headers.get("x-real-ip") or (
        request.client.host if request.client else "sconosciuto"
    )
    esito = await reg.ricevi(
        dati,
        ip=ip,
        settings=s.iot.cittadini.registrazione,
        destinatari=s.contributi.destinatari,
        invia=partial(invia_testo, s.notifications.email),
    )
    if isinstance(esito, reg.Chiusa):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="le registrazioni dei sensori non sono ancora aperte",
        )
    if isinstance(esito, reg.NonValida):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=esito.motivo)
    if isinstance(esito, reg.TroppiInvii):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="troppe richieste in poco tempo: riprova fra un'ora",
        )
    if isinstance(esito, reg.NonPartita):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="la richiesta non è partita: riprova fra qualche minuto",
        )
    return RegistrazioneRisposta(ricevuta=True)
