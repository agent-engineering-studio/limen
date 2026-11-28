"""I dati geografici di base ISPRA, scaricati per lo stack GeoServer.

L'inventario frane IFFI (cinque layer per ognuna delle 21 aree che IdroGEO
pubblica: le regioni, più Bolzano e Trento) e i mosaici nazionali di
pericolosità (PAI frane e idraulica), nella cartella che ``geoserver-init``
carica nel PostGIS di GeoServer (``GEOSERVER_SHAPEFILE_DIR``) e da cui
``geoserver-sync`` li porta in Limen. Prima erano shapefile copiati a mano,
che un server nuovo non sapeva ricostruire. Bolzano e Trento servono a
GeoServer ma non arrivano a Limen: l'AOI è ``it-trentino-alto-adige`` e il
loader cerca tabelle con quel nome, che IdroGEO non pubblica.

Regione per regione e non con il file nazionale: ``geoserver_source`` legge
le tabelle ``<layer>_<regione>_opendata`` e costruisce gli id delle frane dal
loro nome, quindi un file nazionale avrebbe portato un secondo id per ogni
frana in ``iffi_landslides``.

URL, cartella persistente e GET condizionale vengono dal pacchetto
``ispra-idrogeo`` (estratto da Limen, Apache-2.0). ISPRA rigenera i file IFFI
ogni notte e l'ETag cambia con loro, quindi un file scaricato da meno di
``GEODATI__RIVALIDA_DOPO_GIORNI`` non si chiede neanche; passata la soglia,
uno davvero invariato (i mosaici) costa un 304. Il download è in streaming
(i mosaici pesano 1,2 e 0,75 GB) e il retry è quello comune di ``_http``.

Solo l'API pubblica di ``ispra_idrogeo`` (#664). «Scaricato da poco» si legge
dalla data dello ZIP, che ``IdroGEO.download`` riscrive solo quando arriva un
file nuovo (un 304 non lo tocca), invece che dal ``.meta.json`` interno alla
libreria. ``IdroGEO.head`` non serve qui: costa una richiesta, ed è proprio
quella che il salto evita. ``IdroGEO.fetch`` farebbe scaricamento ed
estrazione insieme, ma non dice se il file è cambiato (l'esito lo conta) né
distingue un'estrazione fallita da un download fallito: si usano i suoi due
pezzi pubblici, ``download`` ed ``extract``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ispra_idrogeo import (
    LANDSLIDE_LAYERS,
    PROVINCES,
    REGIONS,
    Dataset,
    FileState,
    IdroGEO,
    Mosaic,
    extract,
    iffi_areas,
    mosaic,
    opendata,
)

from limen.config.percorsi import cartella_geoserver
from limen.config.settings import GeodatiSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.geoserver_source.dati_base import pulisci_appoggi, sync_dati_base

log = get_logger(__name__)

#: Le aree con file IFFI propri: le 19 regioni e le due province autonome
#: (il Trentino-Alto Adige non ne ha uno regionale).
AREE: tuple[str, ...] = (*REGIONS.values(), PROVINCES[21], PROVINCES[22])


def dataset(mosaico_pai: Mosaic) -> list[Dataset]:
    """Cosa serve a ``geoserver_source``: 105 file IFFI e 2 mosaici.

    Il mosaico PAI è quello scelto con ``GEODATI__MOSAICO_PAI`` (#670):
    l'altro non si scarica.
    """
    return [*iffi(), mosaic(mosaico_pai), mosaic("idraulica")]


@dataclass
class Esito:
    cambiati: list[str] = field(default_factory=list)
    invariati: int = 0
    falliti: dict[str, str] = field(default_factory=dict)


def _recente(path: Path, giorni: int) -> bool:
    try:
        return time.time() - path.stat().st_mtime < giorni * 86_400
    except OSError:
        return False


async def _uno(idrogeo: IdroGEO, ds: Dataset, dove: Path, esito: Esito, *, giorni: int) -> None:
    estratta = dove / ds.stem
    if estratta.is_dir() and _recente(dove / ds.filename, giorni):
        esito.invariati += 1
        return
    try:
        scaricato = await call_with_retry(lambda: idrogeo.download(ds, dove))
        if scaricato.changed or not estratta.is_dir():
            try:
                await asyncio.to_thread(extract, scaricato.path, estratta)
            except Exception:
                # Uno ZIP rotto con il suo ETag riceverebbe 304 per sempre: via
                # lo ZIP, e senza file la libreria non manda più l'ETag (rifà
                # un GET pieno), così il prossimo giro lo riscarica.
                scaricato.path.unlink(missing_ok=True)
                raise
    except Exception as exc:  # un file che non arriva non ferma gli altri
        log.warning("geodati.file_fallito", file=ds.filename, error=str(exc)[:300])
        esito.falliti[ds.filename] = str(exc)[:300]
        return
    if scaricato.changed:
        esito.cambiati.append(ds.filename)
        log.info("geodati.aggiornato", file=ds.filename)
    else:
        esito.invariati += 1


#: Le aree IFFI delle regioni con questi codici ISTAT (#407): il Trentino-Alto
#: Adige (4) dà Bolzano e Trento. È ``ispra_idrogeo.iffi_areas`` (0.14).
aree_iffi = iffi_areas


def iffi(aree: Iterable[str] = AREE) -> list[Dataset]:
    """I file dell'inventario frane, area per area: 105 per tutta Italia."""
    return [opendata(layer, area) for layer in LANDSLIDE_LAYERS for area in aree]


async def scarica_idrogeo(scelti: list[Dataset], s: GeodatiSettings, dove: Path) -> Esito:
    """Scarica ``scelti`` da IdroGEO in ``dove``; un file che non arriva non ferma gli altri."""
    idrogeo = IdroGEO(await SharedHttpClient.get(), retries=0)
    cancello = asyncio.Semaphore(s.concorrenza)
    esito = Esito()

    async def _con_cancello(ds: Dataset) -> None:
        async with cancello:
            await _uno(idrogeo, ds, dove, esito, giorni=s.rivalida_dopo_giorni)

    await asyncio.gather(*(_con_cancello(ds) for ds in scelti))
    return esito


async def sync_geodati(s: GeodatiSettings) -> Esito:
    """Tutto quello che geoserver-init carica: IdroGEO, poi ISTAT, CORINE e geolitologia."""
    dove = cartella_geoserver()
    dove.mkdir(parents=True, exist_ok=True)
    pulisci_appoggi(dove)
    esito = await scarica_idrogeo(dataset(s.mosaico_pai), s, dove)
    idrogeo = IdroGEO(await SharedHttpClient.get(), retries=0)
    # Il resto di quello che geoserver-init carica: ISTAT, CORINE, geolitologia.
    scaricati, falliti = await sync_dati_base(idrogeo, dove)
    esito.cambiati.extend(scaricati)
    esito.falliti.update(falliti)
    log.info(
        "geodati.fatto",
        cartella=str(dove),
        cambiati=len(esito.cambiati),
        invariati=esito.invariati,
        falliti=len(esito.falliti),
    )
    return esito


def cambiato(locale: Path, remoto: FileState, *, giorni: int) -> bool:
    """Il file su IdroGEO non è quello caricato, e conta: dimensione diversa.

    Non l'ETag: per nginx è data+dimensione, e ISPRA rigenera ogni notte i
    file IFFI anche a contenuto identico. Un file IFFI conta solo se la copia
    ha passato ``giorni``: il contenuto cambia quasi ogni giorno (87 file su
    107 in 24 giorni, misurato il 27/11/2026) e ``geodati-sync`` lo riprende da
    sé a quella scadenza; oltre, l'aggiornamento non sta girando. Un mosaico
    cambia ogni qualche anno e conta subito.
    """
    try:
        if remoto.size is None or locale.stat().st_size == remoto.size:
            return False
    except OSError:
        return False
    return remoto.filename.startswith("Mosaicatura") or not _recente(locale, giorni)


async def cambiati_su_ispra(s: GeodatiSettings) -> list[str] | None:
    """I file ISPRA caricati che su IdroGEO sono cambiati, senza scaricarli (#672).

    Una richiesta ``HEAD`` per file, solo per quelli che sono nella cartella:
    un'installazione senza dati ISPRA non chiede niente. ``None`` se IdroGEO
    non ha risposto a nessuna: non sapere non è «niente di cambiato».
    """
    dove = cartella_geoserver()
    presenti = [ds for ds in dataset(s.mosaico_pai) if (dove / ds.filename).is_file()]
    if not presenti:
        return []
    idrogeo = IdroGEO(await SharedHttpClient.get(), retries=0)
    cancello = asyncio.Semaphore(s.concorrenza)

    async def _uno(ds: Dataset) -> FileState | None:
        async with cancello:
            try:
                return await call_with_retry(lambda: idrogeo.head(ds))
            except Exception as exc:
                log.warning("geodati.head_fallita", file=ds.filename, error=str(exc)[:300])
                return None

    stati = await asyncio.gather(*(_uno(ds) for ds in presenti))
    letti = [st for st in stati if st is not None]
    if not letti:
        log.warning("integration.degraded", source="idrogeo", op="freschezza")
        return None
    return sorted(
        st.filename
        for st in letti
        if cambiato(dove / st.filename, st, giorni=s.rivalida_dopo_giorni)
    )


__all__ = [
    "AREE",
    "Esito",
    "aree_iffi",
    "cambiati_su_ispra",
    "cambiato",
    "dataset",
    "iffi",
    "scarica_idrogeo",
    "sync_geodati",
]
