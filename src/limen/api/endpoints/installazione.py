"""L'installazione guidata: cosa serve a Limen e a che punto è (#404, epic #409).

``GET /api/installazione/stato`` è pubblico come il resto della mappa: dice
quali dati servono, a cosa, quanti ce ne sono e cosa manca a ogni pericolo.
``POST /api/installazione/download`` cambia qualcosa — mette in coda un
download che il worker eseguirà — e chiede il token di installazione (#403),
come ``POST /api/installazione/elabora``, che rimette in coda il caricamento
nelle celle dei file già scaricati (#405), e ``POST /api/installazione/regioni``,
che aggiunge regioni da monitorare (#407). ``GET /api/installazione/salute``
(#408) è la stessa pagina a installazione finita: le fonti, le quote, le
celle non misurate, il disco, il backup. Pubblica: niente chiavi, niente importi.

Nessuna logica qui: catalogo, copertura, coda e prontezza stanno in
``config``, ``data/repos`` e ``core``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from limen.api.dependencies import SettingsDep, TokenInstallazioneDep
from limen.api.jobs.ids import JOB_NIGHTLY, JOB_WORKER_HEARTBEAT
from limen.api.schemas import (
    DiscoSalute,
    DownloadDato,
    FonteSalute,
    InstallazioneStato,
    NonMisurate,
    PassoSalute,
    PericoloPronto,
    RegioneInstallazione,
    RichiestaDownload,
    RichiestaRegioni,
    RispostaDownload,
    SaluteStato,
    VoceDato,
)
from limen.config.catalogo_dati import carica_catalogo
from limen.core import salute as regole
from limen.core.installazione import (
    byte_stimati,
    mancanti,
    regioni_da_verificare,
    regioni_senza,
    scaricabili,
)
from limen.core.models.hazard import HazardType
from limen.data.repos import copertura_repo, job_runs_repo, salute_repo
from limen.data.repos import dati_download_repo as coda
from limen.data.seed.loader import load_regions
from limen.integrations.openmeteo.flood import pausa_glofas_fino
from limen.integrations.salute import FONTI

router = APIRouter(prefix="/api/installazione", tags=["installazione"])


def _dto(riga: coda.StatoDownload | None) -> DownloadDato | None:
    if riga is None:
        return None
    return DownloadDato(
        stato=riga.stato,
        byte_fatti=riga.byte_fatti,
        byte_totali=riga.byte_totali,
        aggiornato_il=riga.aggiornato_il,
        errore=riga.errore,
    )


@router.get("/stato", response_model=InstallazioneStato)
async def stato(settings: SettingsDep) -> InstallazioneStato:
    catalogo = carica_catalogo()
    copertura = await copertura_repo.leggi(catalogo)
    scaricamenti = {r.voce: r for r in await coda.elenco()}
    senza = regioni_senza(catalogo, copertura.per_regione)
    sospette = regioni_da_verificare(
        catalogo,
        copertura.per_regione,
        copertura.informativi_per_regione,
        copertura.celle_per_regione,
    )
    return InstallazioneStato(
        celle_totali=copertura.celle_totali,
        regioni=copertura.regioni,
        elenco_regioni=[
            RegioneInstallazione(
                id=r.id,
                nome=r.name,
                celle=copertura.celle_per_regione.get(r.id, 0),
                semina=_dto(scaricamenti.get(coda.PREFISSO_REGIONE + r.id)),
            )
            for r in sorted(load_regions(), key=lambda r: r.name)
        ],
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
                conta=v.misura.conta,
                regioni_senza=senza.get(v.id, []),
                regioni_da_verificare=sospette.get(v.id, []),
                download=_dto(scaricamenti.get(v.id)),
            )
            for v in catalogo.voci
        ],
        elaborazione=_dto(scaricamenti.get(coda.ELABORAZIONE)),
        azioni_abilitate=settings.installazione.abilitato,
    )


_DISCHI = {"dati": "Dati (LIMEN_DATA_ROOT)", "docker": "Docker (volume di Postgres)"}


def _passo(run: job_runs_repo.JobRun) -> PassoSalute:
    stato, nota = regole.passo(run)
    return PassoSalute(
        nome=run.scope or run.job_id, stato=stato, finito_il=run.finished_at, nota=nota
    )


@router.get("/salute", response_model=SaluteStato)
async def salute(settings: SettingsDep) -> SaluteStato:
    righe = [r for r in await salute_repo.fonti() if r.fonte in FONTI]
    fonti = [
        FonteSalute(
            id=r.fonte,
            nome=FONTI[r.fonte].nome,
            pericoli=list(FONTI[r.fonte].pericoli),
            ultimo_ok=r.ultimo_ok,
            ultimo_errore=r.ultimo_errore,
            errore=r.errore,
            in_errore=regole.in_errore(r.ultimo_ok, r.ultimo_errore),
        )
        for r in sorted(righe, key=lambda r: list(FONTI).index(r.fonte))
    ]
    guaste = [f.id for f in fonti if f.in_errore]
    battiti = await job_runs_repo.recent(JOB_WORKER_HEARTBEAT, limit=1)
    battito = battiti[0] if battiti else None
    m = battito.metrics if battito else {}
    notturno = [_passo(r) for r in await job_runs_repo.latest_per_scope(JOB_NIGHTLY)]
    return SaluteStato(
        fonti=fonti,
        openmeteo="locale" if settings.openmeteo.forecast_url else "pubblica",
        glofas_in_pausa_fino=await pausa_glofas_fino(),
        non_misurate=[
            NonMisurate(
                pericolo=HazardType(p),
                celle=c.non_misurate,
                totali=c.totali,
                cause=regole.cause(HazardType(p), guaste) if c.non_misurate else [],
            )
            for p, c in sorted((await salute_repo.misurate()).items())
        ],
        dischi=[
            DiscoSalute(
                nome=nome,
                libero_gb=float(m[f"disco_{k}_libero_gb"]),
                totale_gb=float(m[f"disco_{k}_totale_gb"]),
            )
            for k, nome in _DISCHI.items()
            if f"disco_{k}_libero_gb" in m
        ],
        db_gb=await salute_repo.dimensione_db_gb(),
        battito=battito.started_at if battito else None,
        backup=next((p for p in notturno if p.nome == "backup"), None),
        notturno=notturno,
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


@router.post("/elabora", response_model=RispostaDownload, status_code=202)
async def elabora(_: TokenInstallazioneDep) -> RispostaDownload:
    """Rimette in coda il caricamento nelle celle: senza scaricare niente."""
    accodate = await coda.accoda([coda.ELABORAZIONE], byte_totali={})
    return RispostaDownload(accodate=accodate, gia_in_corso=[] if accodate else [coda.ELABORAZIONE])


@router.post("/regioni", response_model=RispostaDownload, status_code=202)
async def regioni(richiesta: RichiestaRegioni, _: TokenInstallazioneDep) -> RispostaDownload:
    """Mette in coda la semina delle regioni; poi il worker porta i dati nelle celle."""
    note = {r.id for r in load_regions()}
    if ignote := sorted(set(richiesta.regioni) - note):
        raise HTTPException(status_code=422, detail=f"Regioni sconosciute: {', '.join(ignote)}")
    voci = [coda.PREFISSO_REGIONE + r for r in dict.fromkeys(richiesta.regioni)]
    accodate = await coda.accoda(voci, byte_totali={})
    return RispostaDownload(accodate=accodate, gia_in_corso=sorted(set(voci) - set(accodate)))


__all__ = ["router"]
