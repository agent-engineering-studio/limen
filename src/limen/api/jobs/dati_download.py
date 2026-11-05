"""I download dei dati statici, eseguiti dal worker (#402, epic #409).

Non è una cadenza: un download parte quando qualcuno lo chiede (oggi
``limen dati scarica``, domani la pagina di installazione), quindi il worker
non lo schedula ma lo **ascolta** — ``LISTEN dati_download`` — e all'avvio
riprende quello che un riavvio aveva interrotto. Uno alla volta: le sorgenti
sono servizi pubblici, e due download da 20 GB in parallelo non finirebbero
prima.

L'avanzamento non chiede niente ai downloader, che sono di tre moduli e di un
pacchetto esterno (``ispra-idrogeo``): un osservatore misura ogni pochi
secondi i file che la voce sta scrivendo (``.part`` compresi) e lo salva.
Il totale è il ``peso_gb`` del catalogo, una stima dichiarata come tale.

Un file scaricato non è ancora un dato: finita la coda, se qualcosa è arrivato,
il consumatore accoda l'**elaborazione** (#405), che porta i file nelle celle.
Gira in un processo a parte: per tutta Italia sono ore di raster, e nel processo
del worker terrebbero fermo lo sweep orario. I fattori per cella sono idempotenti
sul costo, quindi rifarla dopo un download piccolo non ricalcola i raster.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import shutil
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx
from ispra_idrogeo import Dataset
from ispra_idrogeo.sources import Mosaic

from limen.config.catalogo_dati import CatalogoDati, carica_catalogo
from limen.config.percorsi import cartella_geoserver, radice_dati
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import dati_download_repo as repo

log = get_logger(__name__)

#: Ogni quanto l'osservatore scrive i byte scaricati.
INTERVALLO_AVANZAMENTO_S = 5.0
#: Se un NOTIFY si perde, la coda si rilegge comunque entro questo tempo.
ATTESA_MASSIMA_S = 300.0
#: Dopo un errore del database il consumatore riprova, non muore.
PAUSA_DOPO_ERRORE_S = 30.0
#: Lo script dei dati statici, dove lo mette l'immagine.
_SCRIPT_STATICI = "/app/scripts/load_static_data.sh"
#: Dopo i fattori per cella: quello che lo script lascia a `nuovo_host.sh`.
_PASSI_FINALI = ("seed-comuni", "ingest-events", "calibrate")


class DownloadFallitoError(RuntimeError):
    """Un errore già scritto per chi installa."""


@dataclass(frozen=True, slots=True)
class Procuratore:
    scarica: Callable[[], Awaitable[None]]
    #: I file e le cartelle che il download scrive, per misurarne l'avanzamento.
    file: Callable[[], Iterable[Path]]


def _idrogeo(scelti: Callable[[], list[Dataset]]) -> Callable[[], Awaitable[None]]:
    async def scarica() -> None:
        from limen.integrations.idrogeo.geodati import scarica_idrogeo

        dove = cartella_geoserver()
        dove.mkdir(parents=True, exist_ok=True)
        esito = await scarica_idrogeo(scelti(), get_settings().geodati, dove)
        if esito.falliti:
            primo = next(iter(esito.falliti.values()))
            raise DownloadFallitoError(
                f"{len(esito.falliti)} file su {len(scelti())} non sono arrivati da IdroGEO "
                f"(il primo: {primo[:150]}). Riprova: quelli già scaricati non si riscaricano."
            )

    return scarica


def _mosaico(nome: Mosaic) -> list[Dataset]:
    from ispra_idrogeo import mosaic

    return [mosaic(nome)]


def _iffi() -> list[Dataset]:
    from limen.integrations.idrogeo.geodati import iffi

    return list(iffi())


async def _dtm() -> None:
    from limen.integrations.geoserver_source.dati_base import dtm

    dove = cartella_geoserver()
    # Il mosaico rielaborato di `make dtm-vrt` vale quanto il file di Zenodo:
    # `load_static_data.sh` lo preferisce, e `dtm()` da solo non lo vede —
    # 22 GB riscaricati per niente.
    if (dove / "dtm" / "dtm5m.vrt").exists():
        return
    await dtm(dove)


async def _corine() -> None:
    from ispra_idrogeo import IdroGEO

    from limen.integrations._http import SharedHttpClient
    from limen.integrations.geoserver_source.dati_base import corine, corine_raster

    dove = cartella_geoserver()
    await corine(IdroGEO(await SharedHttpClient.get(), retries=0), dove)
    await corine_raster(dove)


async def _confini_comuni() -> None:
    from ispra_idrogeo import IdroGEO

    from limen.integrations._http import SharedHttpClient
    from limen.integrations.geoserver_source.dati_base import istat

    dove = cartella_geoserver()
    dove.mkdir(parents=True, exist_ok=True)
    await istat(IdroGEO(await SharedHttpClient.get(), retries=0), dove)


async def _litologia() -> None:
    from limen.integrations.geoserver_source.dati_base import geolitologia

    await geolitologia(cartella_geoserver())


async def _impermeabilizzazione() -> None:
    from limen.integrations.imperviousness.fetch import _resolve_dest, fetch_imperviousness

    if _resolve_dest(None).exists():
        return
    if await fetch_imperviousness() is None:
        raise DownloadFallitoError(
            "Nessuna regione seminata: il riquadro da scaricare viene dalle regioni. "
            "Esegui prima `limen seed`."
        )


def _cartella_impermeabilizzazione() -> list[Path]:
    from limen.integrations.imperviousness.fetch import _resolve_dest

    return [_resolve_dest(None).parent]


async def _strade() -> None:
    from limen.cli.fetch_static import OSM_PBF_URL, OSM_PBF_URL_ENV, _leggi, _scrivi, osm

    radice = radice_dati()
    radice.mkdir(parents=True, exist_ok=True)
    manifest = _leggi(radice)
    await osm(radice, manifest, os.environ.get(OSM_PBF_URL_ENV) or OSM_PBF_URL)
    _scrivi(radice, manifest)


async def _perimetri_effis() -> None:
    from limen.cli.effis_sync import sincronizza
    from limen.data.repos.aoi_repo import list_aoi_ids

    regioni = len(await list_aoi_ids())
    if not regioni:
        raise DownloadFallitoError(
            "Nessuna regione seminata: i perimetri si cercano regione per regione. "
            "Esegui prima `limen seed`."
        )
    conti = await sincronizza(forzato=False)
    if conti["falliti"]:
        raise DownloadFallitoError(
            f"EFFIS non ha risposto per {conti['falliti']} regioni su {regioni}: riprova."
        )


def procuratori() -> dict[str, Procuratore]:
    """Come si procura ogni voce del catalogo che si scarica.

    Le voci derivate (``deriva_da``) non sono qui: si calcolano, non si
    scaricano. Un test controlla che ogni altra voce ci sia.
    """
    from ispra_idrogeo import MOSAICS

    def gs(*nomi: str) -> Callable[[], list[Path]]:
        return lambda: [p for nome in nomi for p in cartella_geoserver().glob(nome)]

    return {
        "iffi": Procuratore(_idrogeo(_iffi), gs("*_opendata.zip*")),
        "pai_frana": Procuratore(
            _idrogeo(lambda: _mosaico("pai_frane")), gs(f"{MOSAICS['pai_frane']}.zip*")
        ),
        "idraulica": Procuratore(
            _idrogeo(lambda: _mosaico("idraulica")), gs(f"{MOSAICS['idraulica']}.zip*")
        ),
        "dtm": Procuratore(_dtm, gs("dtm/HRDTM5m.tif*")),
        "corine": Procuratore(_corine, gs("clc2018_it", "clc2018_it.part")),
        "litologia": Procuratore(_litologia, gs("carta_geolitologica*")),
        "comuni": Procuratore(_confini_comuni, gs("Limiti01012023_g*")),
        "impermeabilizzazione": Procuratore(_impermeabilizzazione, _cartella_impermeabilizzazione),
        "strade": Procuratore(_strade, lambda: [radice_dati() / "osm"]),
        "perimetri_effis": Procuratore(_perimetri_effis, list),
    }


def misura_byte(percorsi: Iterable[Path]) -> int:
    """I byte su disco sotto ``percorsi``: file, o tutto il contenuto delle cartelle."""
    totale = 0
    for p in percorsi:
        try:
            if p.is_dir():
                totale += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
            elif p.is_file():
                totale += p.stat().st_size
        except OSError:  # un .part rinominato mentre lo si misura
            continue
    return totale


def messaggio(exc: BaseException, fonte: str) -> str:
    """L'errore come lo legge chi installa. Il traceback resta nei log."""
    if isinstance(exc, DownloadFallitoError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        codice = exc.response.status_code
        if codice == 404:
            return (
                f"{fonte} non ha più il file all'indirizzo previsto (errore 404): "
                "serve un aggiornamento di Limen."
            )
        if codice in (401, 403):
            return f"{fonte} rifiuta l'accesso (errore {codice}): serve una chiave o un account."
        if codice == 429:
            return f"{fonte} ha ricevuto troppe richieste (errore 429): riprova più tardi."
        return f"Il server di {fonte} ha un problema (errore {codice}): riprova più tardi."
    if isinstance(exc, httpx.TimeoutException):
        return f"Il server di {fonte} non ha risposto in tempo: riprova più tardi."
    if isinstance(exc, httpx.TransportError):
        return f"Impossibile raggiungere {fonte}: controlla che il server abbia accesso a Internet."
    if isinstance(exc, PermissionError):
        return (
            f"Limen non può scrivere in {exc.filename}: la cartella deve essere scrivibile "
            "dall'utente del worker."
        )
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return "Spazio su disco esaurito: libera spazio sotto LIMEN_DATA_ROOT e riprova."
    if isinstance(exc, RuntimeError):
        # I downloader di Limen scrivono già i loro errori in italiano.
        return str(exc)[:300]
    return (
        f"Errore imprevisto ({type(exc).__name__}) scaricando da {fonte}: "
        "il dettaglio è nei log del worker."
    )


async def _esegui_passo(nome: str, *comando: str, ambiente: dict[str, str]) -> str | None:
    """Il nome del passo se è fallito. L'output va nei log del worker."""
    log.info("dati_elaborazione.passo", passo=nome)
    processo = await asyncio.create_subprocess_exec(*comando, env=ambiente)
    try:
        codice = await processo.wait()
    except asyncio.CancelledError:
        # Il worker si sta fermando: l'elaborazione riparte al prossimo avvio,
        # e due giri insieme scriverebbero sulle stesse tabelle.
        with contextlib.suppress(ProcessLookupError):
            processo.terminate()
        raise
    if codice != 0:
        log.warning("dati_elaborazione.passo_fallito", passo=nome, codice=codice)
        return nome
    return None


async def elabora_dati() -> None:
    """Porta nelle celle i file scaricati, con lo script di sempre.

    Un passo fallito non ferma gli altri: la calibrazione sui fattori che ci
    sono vale più di una pagina ferma, e ogni passo si può rifare.
    """
    bash = shutil.which("bash") or "bash"
    limen = shutil.which("limen") or "limen"
    ambiente = os.environ | {"LIMEN_STATICI": "qui", "LIMEN_STATICI_SCARICA": "0"}
    passi = list(_PASSI_FINALI)
    # La catena FWI parte dall'archivio ERA5: settimane di giorni per ogni nodo,
    # che sull'API pubblica consumerebbero il tetto giornaliero dello sweep.
    if get_settings().openmeteo.archive_url:
        passi.append("fwi-backfill")
    else:
        log.info("dati_elaborazione.fwi_saltato", motivo="nessuna istanza Open-Meteo propria")
    falliti = [
        await _esegui_passo("fattori per cella", bash, _SCRIPT_STATICI, ambiente=ambiente),
        *[await _esegui_passo(p, limen, p, ambiente=ambiente) for p in passi],
    ]
    if nomi := [f for f in falliti if f is not None]:
        raise DownloadFallitoError(
            f"Non è riuscito: {', '.join(nomi)}. Il dettaglio è nei log del worker; "
            "si può riprovare, i fattori già calcolati non si ricalcolano."
        )


class ConsumatoreDownload:
    """Il task del worker che esegue la coda dei download."""

    def __init__(
        self,
        *,
        catalogo: CatalogoDati | None = None,
        da_procurare: dict[str, Procuratore] | None = None,
        intervallo_s: float = INTERVALLO_AVANZAMENTO_S,
        elabora: Callable[[], Awaitable[None]] = elabora_dati,
    ) -> None:
        # Caricati al primo uso, dentro il ciclo protetto: un `dati.yaml`
        # malformato deve spegnere i download, non il worker e lo sweep orario.
        self._catalogo = catalogo
        self._procuratori = da_procurare
        self._intervallo_s = intervallo_s
        self._elabora = elabora
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._ciclo())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(BaseException):
                await self._task

    async def _ciclo(self) -> None:
        while True:
            try:
                if self._catalogo is None:
                    self._catalogo = carica_catalogo()
                if self._procuratori is None:
                    self._procuratori = procuratori()
                riprese = await repo.riaccoda_interrotte()
                if riprese:
                    log.info("dati_download.riprese", voci=riprese)
                await self._ascolta()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning(
                    "dati_download.consumatore_fermo",
                    error=str(exc)[:300],
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(PAUSA_DOPO_ERRORE_S)

    async def _ascolta(self) -> None:
        sveglia = asyncio.Event()

        def _notifica(*_: object) -> None:
            sveglia.set()

        async with acquire() as conn:
            await conn.add_listener(repo.CANALE, _notifica)
            try:
                while True:
                    # Prima di svuotare la coda, non dopo: un NOTIFY che arriva
                    # mentre si scarica fa ripassare subito, invece di perdersi.
                    sveglia.clear()
                    await self.svuota_coda()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(sveglia.wait(), timeout=ATTESA_MASSIMA_S)
            finally:
                await conn.remove_listener(repo.CANALE, _notifica)

    async def svuota_coda(self) -> None:
        arrivato = False
        while True:
            voce = await repo.prendi_prossima()
            if voce is None:
                if not arrivato:
                    return
                # In coda e non chiamata qui: un riavvio la riprende come ogni voce.
                arrivato = False
                await repo.accoda([repo.ELABORAZIONE], byte_totali={})
            elif voce == repo.ELABORAZIONE:
                # Chiesta a mano durante un download: copre anche quel download.
                arrivato = False
                await self.elabora()
            elif await self.esegui(voce):
                arrivato = True

    async def elabora(self) -> None:
        async with repo.blocco_download() as libero:
            if not libero:
                await repo.chiudi(
                    repo.ELABORAZIONE,
                    errore=(
                        "Un download (`make static-data` o `limen geodati-sync`) sta scrivendo "
                        "i file da caricare: riprova quando ha finito."
                    ),
                )
                return
            errore: str | None = None
            try:
                await self._elabora()
            except Exception as exc:
                errore = (
                    str(exc)
                    if isinstance(exc, DownloadFallitoError)
                    else f"Errore imprevisto ({type(exc).__name__}): il dettaglio è nei log "
                    "del worker."
                )
                log.warning(
                    "dati_elaborazione.errore",
                    error=str(exc)[:300],
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
            await repo.chiudi(repo.ELABORAZIONE, errore=errore)
            log.info("dati_elaborazione.fine", ok=errore is None)

    async def esegui(self, voce: str) -> bool:
        """Scarica la voce; ``True`` se ora c'è qualcosa da portare nelle celle."""
        catalogo = self._catalogo or carica_catalogo()
        procuratori_ = self._procuratori if self._procuratori is not None else procuratori()
        procuratore = procuratori_.get(voce)
        if procuratore is None:
            await repo.chiudi(
                voce, errore="Questo dato non si scarica: Limen lo calcola da un altro."
            )
            return False
        async with repo.blocco_download() as libero:
            if not libero:
                await repo.chiudi(
                    voce,
                    errore=(
                        "Un altro download (`make static-data` o `limen geodati-sync`) "
                        "sta scrivendo negli stessi file: riprova quando ha finito."
                    ),
                )
                return False
            return await self._scarica(voce, procuratore, catalogo.voce(voce).fonte)

    async def _scarica(self, voce: str, procuratore: Procuratore, fonte: str) -> bool:
        log.info("dati_download.inizio", voce=voce)
        osservatore = asyncio.create_task(self._osserva(voce, procuratore))
        errore: str | None = None
        try:
            await procuratore.scarica()
        except Exception as exc:
            errore = messaggio(exc, fonte)
            log.warning(
                "dati_download.errore",
                voce=voce,
                error=str(exc)[:300],
                error_type=type(exc).__name__,
                exc_info=True,
            )
        finally:
            osservatore.cancel()
            with contextlib.suppress(BaseException):
                await osservatore
        fatti = await asyncio.to_thread(misura_byte, list(procuratore.file()))
        await repo.chiudi(voce, errore=errore, byte_fatti=fatti)
        log.info("dati_download.fine", voce=voce, ok=errore is None, byte=fatti)
        return errore is None

    async def _osserva(self, voce: str, procuratore: Procuratore) -> None:
        while True:
            fatti = await asyncio.to_thread(misura_byte, list(procuratore.file()))
            await repo.avanza(voce, fatti)
            await asyncio.sleep(self._intervallo_s)


__all__ = [
    "ConsumatoreDownload",
    "DownloadFallitoError",
    "Procuratore",
    "elabora_dati",
    "messaggio",
    "misura_byte",
    "procuratori",
]
