"""L'installazione guidata: cosa serve a Limen e a che punto è (#404, epic #409).

``GET /api/installazione/stato`` è pubblico come il resto della mappa: dice
quali dati servono, a cosa, quanti ce ne sono e cosa manca a ogni pericolo.
``POST /api/installazione/download`` cambia qualcosa — mette in coda un
download che il worker eseguirà — e chiede il token di installazione (#403).

Nessuna logica qui: catalogo, copertura, coda e prontezza stanno in
``config``, ``data/repos`` e ``core``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from limen.api.dependencies import SettingsDep, TokenInstallazioneDep
from limen.api.schemas import (
    DownloadDato,
    InstallazioneStato,
    PericoloPronto,
    RichiestaDownload,
    RispostaDownload,
    VoceDato,
)
from limen.config.catalogo_dati import carica_catalogo
from limen.core.installazione import byte_stimati, mancanti, regioni_senza, scaricabili
from limen.data.repos import copertura_repo
from limen.data.repos import dati_download_repo as coda

router = APIRouter(prefix="/api/installazione", tags=["installazione"])


@router.get("/stato", response_model=InstallazioneStato)
async def stato(settings: SettingsDep) -> InstallazioneStato:
    catalogo = carica_catalogo()
    copertura = await copertura_repo.leggi(catalogo)
    scaricamenti = {r.voce: r for r in await coda.elenco()}
    senza = regioni_senza(catalogo, copertura.per_regione)
    return InstallazioneStato(
        celle_totali=copertura.celle_totali,
        regioni=copertura.regioni,
        pericoli=[
            PericoloPronto(pericolo=h, pronto=not ids, mancano=ids)
            for h, ids in mancanti(
                catalogo, totali=copertura.totali, per_regione=copertura.per_regione
            ).items()
        ],
        voci=[
            VoceDato(
                id=v.id,
                nome=v.nome,
                a_cosa_serve=v.a_cosa_serve,
                pericoli=list(v.pericoli),
                livello=v.livello,
                fonte=v.fonte,
                url=v.url,
                licenza=v.licenza,
                attribuzione=v.attribuzione,
                peso_gb=v.peso_gb,
                deriva_da=v.deriva_da,
                copertura=copertura.totali.get(v.id, 0),
                regioni_senza=senza.get(v.id, []),
                download=(
                    None
                    if (r := scaricamenti.get(v.id)) is None
                    else DownloadDato(
                        stato=r.stato,
                        byte_fatti=r.byte_fatti,
                        byte_totali=r.byte_totali,
                        aggiornato_il=r.aggiornato_il,
                        errore=r.errore,
                    )
                ),
            )
            for v in catalogo.voci
        ],
        azioni_abilitate=settings.installazione.abilitato,
    )


@router.post("/download", response_model=RispostaDownload, status_code=202)
async def download(richiesta: RichiestaDownload, _: TokenInstallazioneDep) -> RispostaDownload:
    """Mette in coda le voci; le scarica il worker, una alla volta."""
    catalogo = carica_catalogo()
    try:
        voci = scaricabili(catalogo, richiesta.voci)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    accodate = await coda.accoda(voci, byte_totali=byte_stimati(catalogo))
    return RispostaDownload(accodate=accodate, gia_in_corso=sorted(set(voci) - set(accodate)))


__all__ = ["router"]
