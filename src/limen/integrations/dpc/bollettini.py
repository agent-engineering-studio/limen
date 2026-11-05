"""Il Bollettino di criticità nazionale/allerta della Protezione Civile.

Pubblicato ogni giorno entro le 16:00 nel repository GitHub del Dipartimento
(`pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica`, CC-BY 4.0), come
GeoJSON per oggi e per domani. È già strutturato: nessun modello linguistico
lo legge, lo si importa.

Nomi dei file, livelli e zone vengono dal pacchetto ``dpc-radar``
(``dpc_radar.bulletins``); qui si usano solo le sue parti pure, perché le
richieste passino da ``_http``.

La lettura degrada a un risultato neutro (``None``) se GitHub non risponde:
il confronto con l'allerta ufficiale è un'informazione in più, non una
condizione per far girare il resto.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
from dpc_radar.bulletins import API, RAW, Bulletin, issued, latest_name_from, zones_from_geojson

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)


async def _json(url: str) -> Any:
    resp = await fetch_with_retry("GET", url, client=await SharedHttpClient.get())
    return resp.json()


async def ultimo_nome() -> str | None:
    """Il nome dell'ultimo bollettino pubblicato, o ``None``.

    Tre chiamate piccole all'albero del repository invece di una ricorsiva:
    l'archivio ha decine di migliaia di file.
    """
    try:
        radice = await _json(f"{API}/git/trees/master")
        files = next(t["sha"] for t in radice["tree"] if t["path"] == "files")
        sotto = await _json(f"{API}/git/trees/{files}")
        geojson = next(t["sha"] for t in sotto["tree"] if t["path"] == "geojson")
        elenco = await _json(f"{API}/git/trees/{geojson}")
    except (httpx.HTTPError, KeyError, StopIteration, ValueError) as exc:
        log.warning("integration.degraded", source="dpc_bollettini", error=str(exc))
        return None
    return latest_name_from(elenco)


async def scarica(nome: str) -> Bulletin | None:
    """Oggi e domani del bollettino ``nome``, o ``None`` se non si legge."""
    emesso = issued(nome)
    if emesso is None:
        return None
    radice = nome.removesuffix("_today.json")
    giorno = emesso.date()
    try:
        oggi = await _json(f"{RAW}/{radice}_today.json")
        domani = await _json(f"{RAW}/{radice}_tomorrow.json")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("integration.degraded", source="dpc_bollettini", file=nome, error=str(exc))
        return None
    zone = zones_from_geojson(oggi, giorno) + zones_from_geojson(domani, giorno + timedelta(days=1))
    return Bulletin(name=radice, issued=emesso, zones=zone)
