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
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ispra_idrogeo import (
    LANDSLIDE_LAYERS,
    MOSAICS,
    PROVINCES,
    REGIONS,
    Dataset,
    IdroGEO,
    extract,
    mosaic,
    opendata,
)
from ispra_idrogeo.cache import meta_path

from limen.config.percorsi import cartella_geoserver
from limen.config.settings import GeodatiSettings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.geoserver_source.dati_base import pulisci_appoggi, sync_dati_base

log = get_logger(__name__)

#: Le aree con file IFFI propri: le 19 regioni e le due province autonome
#: (il Trentino-Alto Adige non ne ha uno regionale).
AREE: tuple[str, ...] = (*REGIONS.values(), PROVINCES[21], PROVINCES[22])


def dataset() -> list[Dataset]:
    """Cosa serve a ``geoserver_source``: 105 file IFFI e 2 mosaici."""
    return [*iffi(), *(mosaic(nome) for nome in MOSAICS)]


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
    if estratta.is_dir() and _recente(meta_path(dove / ds.filename), giorni):
        esito.invariati += 1
        return
    try:
        scaricato = await call_with_retry(lambda: idrogeo.download(ds, dove))
        if scaricato.changed or not estratta.is_dir():
            try:
                await asyncio.to_thread(extract, scaricato.path, estratta)
            except Exception:
                # Uno ZIP rotto con il suo ETag riceverebbe 304 per sempre:
                # via tutti e due, così il prossimo giro lo riscarica.
                scaricato.path.unlink(missing_ok=True)
                meta_path(scaricato.path).unlink(missing_ok=True)
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


#: Il Trentino-Alto Adige (ISTAT 4) ha i file delle due province, non uno suo.
_TRENTINO_ALTO_ADIGE = 4


def aree_iffi(cod_reg: Iterable[int]) -> tuple[str, ...]:
    """Le aree IFFI delle regioni con questi codici ISTAT (#407)."""
    aree: list[str] = []
    for c in cod_reg:
        if c == _TRENTINO_ALTO_ADIGE:
            aree += [PROVINCES[21], PROVINCES[22]]
        elif c in REGIONS:
            aree.append(REGIONS[c])
    return tuple(aree)


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
    esito = await scarica_idrogeo(dataset(), s, dove)
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


__all__ = ["AREE", "Esito", "aree_iffi", "dataset", "iffi", "scarica_idrogeo", "sync_geodati"]
