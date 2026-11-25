"""ESA WorldCover 2021 sull'Italia, nell'init: la terra che ``firms_client.trust`` legge (#714).

``trust`` dice quanto una rilevazione FIRMS in un punto si può leggere come
incendio di vegetazione: la maschera delle fonti fisse e la copertura del suolo
intorno (bosco, campi, prato, costruito, acqua). La copertura è ESA WorldCover
10 m (2021, v200, CC BY 4.0): letta dal bucket pubblico un blocco alla volta va
in rete a ogni domanda, quindi un server la tiene in locale. Qui si scaricano
le tile intere di 3 gradi per lato che coprono il riquadro di FIRMS
(``FIRMS__BBOX``): sul riquadro di default 25, di cui 23 esistono, 1,3 GB una
volta sola. Una tile di solo mare non esiste (404) e si salta.

Le tile restano col loro nome, sotto ``$DATA_ROOT/firms-client/worldcover``
come nel bucket. Chi le legge passa **sempre** da :func:`worldcover_locale`, e
un ``None`` è «non misurato»: mai ``firms_client.WorldCover.synced()`` né il
default della libreria, che senza tile locali leggerebbero il bucket via GDAL,
fuori da ``_http`` e con un retry loro. Un file già presente non si
riscarica (WorldCover 2021 non cambia); le tile di solo mare, che non
esistono, si richiedono a ogni giro: due risposte 404 e nient'altro.
Il download è quello della libreria (``download_worldcover_tile``: uno stream
in un ``.part`` rinominato a fine file, 404 = mare) un file alla volta, senza
il suo retry, dentro ``call_with_retry`` sul client condiviso, come i mosaici
ISPRA. La libreria mette le tile in ``<cartella>/worldcover/<percorso del
bucket>``: qui la cartella è il genitore di :func:`cartella_worldcover`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import httpx
from firms_client import WorldCover, download_worldcover_tile, worldcover_tiles
from firms_client.init import worldcover_path
from firms_client.landcover import WORLDCOVER_DIR
from tenacity import RetryError

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.firms.archive import cartella_cache

log = get_logger(__name__)


def cartella_worldcover() -> Path:
    """Dove stanno le tile: ``$DATA_ROOT/firms-client/worldcover``, accanto agli archivi FIRMS."""
    return cartella_cache() / WORLDCOVER_DIR


@dataclass(slots=True)
class Esito:
    scaricate: list[str] = field(default_factory=list)
    presenti: list[str] = field(default_factory=list)
    assenti: list[str] = field(default_factory=list)
    fallite: list[str] = field(default_factory=list)


async def scarica_worldcover(
    cartella: Path | None = None, *, client: httpx.AsyncClient | None = None
) -> Esito:
    """Le tile che coprono ``FIRMS__BBOX`` in ``cartella``; quelle già presenti si saltano.

    ``cartella`` si chiama ``worldcover``: è lì che la libreria le cerca.
    """
    cartella = cartella or cartella_worldcover()
    if cartella.name != WORLDCOVER_DIR:
        raise ValueError(f"la cartella delle tile si chiama {WORLDCOVER_DIR!r}: {cartella}")
    http = client or await SharedHttpClient.get()
    esito = Esito()
    for url in worldcover_tiles(get_settings().firms.bbox):
        destinazione = worldcover_path(url, cartella.parent)
        nome = destinazione.name
        if destinazione.exists():
            esito.presenti.append(nome)
            continue
        try:
            scaricata = await call_with_retry(
                partial(download_worldcover_tile, http, url, cartella.parent)
            )
        except (httpx.HTTPError, RetryError, OSError) as errore:
            esito.fallite.append(nome)
            log.error("worldcover.fallita", tile=nome, errore=str(errore))
            continue
        if scaricata is None:
            esito.assenti.append(nome)
        else:
            esito.scaricate.append(nome)
            log.info("worldcover.scaricata", tile=nome, byte=scaricata.stat().st_size)
    return esito


def worldcover_locale(cartella: Path | None = None) -> WorldCover | None:
    """``WorldCover`` sulle tile scaricate, o ``None`` se l'init non le ha ancora portate."""
    cartella = cartella or cartella_worldcover()
    return WorldCover(str(cartella)) if any(cartella.rglob("*.tif")) else None
