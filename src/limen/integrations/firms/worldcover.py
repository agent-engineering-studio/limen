"""ESA WorldCover 2021 sull'Italia, nell'init: la terra che ``firms_client.trust`` legge (#714).

``trust`` dice quanto una rilevazione FIRMS in un punto si può leggere come
incendio di vegetazione: la maschera delle fonti fisse e la copertura del suolo
intorno (bosco, campi, prato, costruito, acqua). La copertura è ESA WorldCover
10 m (2021, v200, CC BY 4.0): letta dal bucket pubblico un blocco alla volta va
in rete a ogni domanda, quindi un server la tiene in locale. Qui si scaricano
le tile intere di 3 gradi per lato che coprono il riquadro di FIRMS
(``FIRMS__BBOX``): sul riquadro di default 25, di cui 23 esistono, 1,3 GB una
volta sola. Una tile di solo mare non esiste (404) e si salta.

Le tile restano col loro nome, sotto ``<LIMEN_DATA_DIR>/landcover/worldcover``
come nel bucket. Chi le legge passa **sempre** da :func:`worldcover_locale`, e
un ``None`` è «non misurato»: mai ``firms_client.WorldCover.synced()`` né il
default della libreria, che senza tile locali leggerebbero il bucket via GDAL,
fuori da ``_http`` e con un retry loro. Un file già presente non si
riscarica (WorldCover 2021 non cambia); le tile di solo mare, che non
esistono, si richiedono a ogni giro: due risposte 404 e nient'altro.
Il download è uno stream di file grandi, quindi passa da ``call_with_retry``
sul client condiviso, come i mosaici ISPRA.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from firms_client import WorldCover
from firms_client.landcover import WORLDCOVER_URL as WORLDCOVER_URL
from tenacity import RetryError

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, call_with_retry

log = get_logger(__name__)

_PEZZO = 1 << 20
#: Il lato di una tile WorldCover, in gradi.
_LATO = 3


def cartella_worldcover() -> Path:
    """Dove stanno le tile: accanto agli archivi FIRMS, sotto ``LIMEN_DATA_DIR``."""
    return Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser() / "landcover" / "worldcover"


def tile_per_riquadro(bbox: tuple[float, float, float, float]) -> list[str]:
    """Gli URL delle tile WorldCover che toccano ``bbox`` (ovest, sud, est, nord)."""
    ovest, sud, est, nord = bbox
    mappa = WorldCover()
    return [
        mappa.tile(lat + _LATO / 2, lon + _LATO / 2)
        for lat in range(math.floor(sud / _LATO) * _LATO, math.ceil(nord / _LATO) * _LATO, _LATO)
        for lon in range(math.floor(ovest / _LATO) * _LATO, math.ceil(est / _LATO) * _LATO, _LATO)
    ]


@dataclass(slots=True)
class Esito:
    scaricate: list[str] = field(default_factory=list)
    presenti: list[str] = field(default_factory=list)
    assenti: list[str] = field(default_factory=list)
    fallite: list[str] = field(default_factory=list)


async def _scarica(client: httpx.AsyncClient, url: str, destinazione: Path) -> bool:
    """Una tile in ``destinazione``; ``False`` se non esiste (mare)."""
    parziale = destinazione.with_name(destinazione.name + ".part")

    async def tentativo() -> bool:
        async with client.stream("GET", url) as risposta:
            if risposta.status_code == 404:  # una tile di solo mare non esiste
                return False
            risposta.raise_for_status()
            destinazione.parent.mkdir(parents=True, exist_ok=True)
            with parziale.open("wb") as out:
                async for pezzo in risposta.aiter_bytes(_PEZZO):
                    out.write(pezzo)
        return True

    try:
        if not await call_with_retry(tentativo):
            return False
        parziale.rename(destinazione)
    finally:
        parziale.unlink(missing_ok=True)
    return True


async def scarica_worldcover(
    cartella: Path | None = None, *, client: httpx.AsyncClient | None = None
) -> Esito:
    """Le tile che coprono ``FIRMS__BBOX`` in ``cartella``; quelle già presenti si saltano."""
    cartella = cartella or cartella_worldcover()
    http = client or await SharedHttpClient.get()
    esito = Esito()
    for url in tile_per_riquadro(get_settings().firms.bbox):
        destinazione = cartella / url.removeprefix(WORLDCOVER_URL + "/")
        nome = destinazione.name
        if destinazione.exists():
            esito.presenti.append(nome)
            continue
        try:
            if await _scarica(http, url, destinazione):
                esito.scaricate.append(nome)
                log.info("worldcover.scaricata", tile=nome, byte=destinazione.stat().st_size)
            else:
                esito.assenti.append(nome)
        except (httpx.HTTPError, RetryError, OSError) as errore:
            esito.fallite.append(nome)
            log.error("worldcover.fallita", tile=nome, errore=str(errore))
    return esito


def worldcover_locale(cartella: Path | None = None) -> WorldCover | None:
    """``WorldCover`` sulle tile scaricate, o ``None`` se l'init non le ha ancora portate."""
    cartella = cartella or cartella_worldcover()
    return WorldCover(str(cartella)) if any(cartella.rglob("*.tif")) else None
