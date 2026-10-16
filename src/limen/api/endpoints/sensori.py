"""Sensori dei cittadini: il modulo di registrazione (#253) e le stazioni sulla mappa (#255)."""

from __future__ import annotations

from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from limen.api.dependencies import DepsDep
from limen.core import sensori_registrazione as reg
from limen.core import sensori_stazioni
from limen.core.models.hazard import HazardType
from limen.data.repos import sensor_devices_repo
from limen.notifications.email import invia_testo

router = APIRouter(tags=["sensori"])


class RegistrazioneStato(BaseModel):
    aperta: bool


class RegistrazioneRisposta(BaseModel):
    ricevuta: bool


@router.get("/api/sensori/stazioni")
async def stazioni(response: Response, hazard: HazardType | None = None) -> dict[str, Any]:
    """Le stazioni in GeoJSON: posizione arrotondata per quelle di terzi, niente dati personali."""
    # Una stazione manda un dato ogni cinque minuti: rifare la query per ogni
    # visitatore non dice niente di più.
    response.headers["Cache-Control"] = "public, max-age=300"
    return sensori_stazioni.geojson(await sensor_devices_repo.stazioni_pubbliche(), hazard)


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
