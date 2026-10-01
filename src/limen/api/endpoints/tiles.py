"""Vector tiles: l'API le **inoltra**, non le rimanda altrove.

La prima versione rispondeva 307 verso `API__PG_TILESERV_URL`, che nel compose
è l'indirizzo interno `http://pg_tileserv:7800`. Il browser quel nome non lo
risolve — e su una pagina servita in `https` un salto in `http` verrebbe
bloccato comunque: la mappa restava senza celle, mentre l'endpoint dal server
rispondeva perfettamente. Il redirect, in più, contraddiceva la ragione per cui
questo endpoint esiste, cioè non far conoscere alla SPA il nome di pg_tileserv:
glielo faceva conoscere per forza, all'ultimo momento e dentro il browser.

Inoltrando i byte, invece, l'origine resta una sola: niente CORS, niente
contenuto misto, nessun nome interno esposto. La tile è un blob da qualche
decina di kB e ne servono poche per schermata, quindi il costo sul processo API
è modesto — è tutt'altra cosa dal macinare 312k celle, che è ciò che l'API non
deve fare.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Query, Response, status

from limen.api.dependencies import DepsDep
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)

router = APIRouter(prefix="/api/tiles", tags=["tiles"])

#: Una tile lenta è una tile inutile: la mappa ne chiede molte insieme e
#: l'utente si muove prima che arrivino.
_TILE_TIMEOUT_SECONDS = 10.0

#: Intestazioni che vale la pena riportare al browser così come sono.
_PASS_THROUGH = ("content-type", "content-encoding", "cache-control", "etag")


@router.get("/{layer}/{z}/{x}/{y}.pbf")
async def tile(
    layer: str,
    z: int,
    x: int,
    y: int,
    deps: DepsDep,
    # I parametri delle sorgenti a funzione. Sono dichiarati uno per uno, e
    # non inoltrati in blocco, perché un proxy che ripete qualunque cosa gli
    # arrivi moltiplica le chiavi di cache a piacere di chi chiama.
    p_hazard: HazardType | None = None,
    hours_ago: int | None = None,
    # Le colonne da includere nelle tile delle sorgenti a tabella. Scartarlo
    # faceva tornare a pg_tileserv **tutte** le colonne — i JSON degli
    # attributi degli eventi, i metadati di caricamento — e le tile dei livelli
    # di contesto perdevano l'ottimizzazione che le rendeva leggere. Validato
    # come elenco di nomi di colonna, per la stessa ragione per cui gli altri
    # parametri sono dichiarati uno per uno: niente chiavi di cache arbitrarie.
    properties: str | None = Query(
        None, max_length=200, pattern=r"^[a-z_][a-z0-9_]*(,[a-z_][a-z0-9_]*)*$"
    ),
) -> Response:
    """Inoltra la tile da ``pg_tileserv``, mantenendo l'origine dell'API.

    **La query string va inoltrata.** La prima versione costruiva l'URL con
    il solo percorso, quindi `p_hazard` non arrivava mai a pg_tileserv e
    `risk_at()` rispondeva sempre con il pericolo di default: il selettore
    mostrava le celle delle frane etichettate «Alluvione». È un guasto
    peggiore della mappa vuota — la mappa vuota si vede, una mappa con i dati
    sbagliati no. Era invisibile finché quelle tile andavano in timeout.
    """
    base = deps.settings.api.pg_tileserv_url
    if not base:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pg_tileserv URL is not configured (set API__PG_TILESERV_URL)",
        )
    url = f"{base.rstrip('/')}/{layer}/{z}/{x}/{y}.pbf"
    # Solo i parametri presenti: `multi_hazard_at` non ne accetta, e
    # passargliene uno sarebbe un 400 su ogni tile del quadro unico.
    params = {
        **({"p_hazard": p_hazard.value} if p_hazard is not None else {}),
        **({"hours_ago": str(hours_ago)} if hours_ago is not None else {}),
        **({"properties": properties} if properties is not None else {}),
    }
    client = await SharedHttpClient.get()
    try:
        upstream = await client.get(url, params=params, timeout=_TILE_TIMEOUT_SECONDS)
    except (httpx.HTTPError, TimeoutError, OSError) as exc:
        # pg_tileserv giù non è un errore del chiamante: la mappa resta senza
        # quel riquadro e lo dice, invece di far sembrare rotta la richiesta.
        log.warning(
            "api.tiles.upstream_unreachable",
            layer=layer,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="pg_tileserv non raggiungibile",
        ) from exc

    headers = {k: v for k, v in upstream.headers.items() if k.lower() in _PASS_THROUGH}
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=headers.get("content-type", "application/vnd.mapbox-vector-tile"),
    )
