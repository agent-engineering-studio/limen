"""Uscite standard di sola lettura: CAP 1.2 (#499) e OGC API Features (#503).

Nessuna logica qui: i documenti li costruisce ``core.standard``, le righe le
legge ``data.repos.standard_repo``. Stanno sotto ``/api/`` perché il proxy
inoltra già quel prefisso.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from limen.core.models.hazard import HazardType
from limen.core.standard import cap, ogc
from limen.data.repos import hazards_repo, standard_repo

router = APIRouter(tags=["standard"])

_XML_ATOM = "application/atom+xml; charset=utf-8"


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.get("/api/cap", response_class=Response, summary="Feed Atom dei messaggi CAP 1.2")
async def cap_feed(request: Request) -> Response:
    cfg = cap.carica_config()
    comuni = await standard_repo.comuni_in_allerta(list(cfg.classi))
    aggiornato = max((c.computed_at for c in comuni), default=datetime.now(UTC))
    corpo = cap.feed_atom(comuni, base_url=_base(request), aggiornato=aggiornato)
    return Response(corpo, media_type=_XML_ATOM, headers={"Cache-Control": "public, max-age=60"})


@router.get("/api/cap/{identificativo}", response_class=Response, summary="Un messaggio CAP 1.2")
async def cap_messaggio(identificativo: str) -> Response:
    parti = cap.da_identificativo(identificativo)
    if parti is None:
        raise HTTPException(404, "identificativo sconosciuto")
    hazard, istat, _ = parti
    cfg = cap.carica_config()
    c = await standard_repo.comune_in_allerta(list(cfg.classi), hazard, istat)
    # Un messaggio vale per il calcolo che lo ha prodotto: dopo il successivo
    # l'identificativo vecchio non c'è più, come un avviso scaduto.
    if c is None or cap.identificativo(c) != identificativo:
        raise HTTPException(404, "messaggio non più valido")
    return Response(cap.messaggio(c, cfg), media_type=cap.MEDIA_TYPE)


def _ogc(request: Request) -> str:
    return f"{_base(request)}/api/ogc"


async def _abilitati() -> list[HazardType]:
    return sorted(await hazards_repo.enabled_hazards(), key=lambda h: h.value)


@router.get("/api/ogc", summary="OGC API Features: pagina iniziale")
async def ogc_landing(request: Request) -> dict[str, Any]:
    return ogc.landing(_ogc(request))


@router.get("/api/ogc/conformance", summary="OGC API Features: conformità")
async def ogc_conformance() -> dict[str, Any]:
    return {"conformsTo": ogc.CONFORMITA}


@router.get("/api/ogc/collections", summary="OGC API Features: collezioni")
async def ogc_collections(request: Request) -> dict[str, Any]:
    return ogc.collezioni(_ogc(request), await _abilitati(), anno=datetime.now(UTC).year)


async def _collezione(id_: str) -> HazardType:
    hazard = ogc.da_id_collezione(id_)
    if hazard is None or hazard not in await _abilitati():
        raise HTTPException(404, "collezione sconosciuta")
    return hazard


@router.get("/api/ogc/collections/{collection_id}", summary="OGC API Features: una collezione")
async def ogc_collection(collection_id: str, request: Request) -> dict[str, Any]:
    hazard = await _collezione(collection_id)
    return ogc.collezione(_ogc(request), hazard, anno=datetime.now(UTC).year)


@router.get(
    "/api/ogc/collections/{collection_id}/items",
    response_class=JSONResponse,
    summary="OGC API Features: i comuni della collezione",
)
async def ogc_items(
    collection_id: str,
    request: Request,
    bbox: Annotated[str | None, Query(description="minx,miny,maxx,maxy in CRS84")] = None,
    datetime_: Annotated[
        str | None, Query(alias="datetime", description="istante o intervallo RFC 3339")
    ] = None,
    limit: Annotated[int | None, Query()] = None,
    offset: Annotated[int | None, Query()] = None,
) -> JSONResponse:
    hazard = await _collezione(collection_id)
    try:
        f = ogc.filtro(bbox=bbox, datetime_=datetime_, limit=limit, offset=offset)
    except ogc.ParametroNonValidoError as exc:
        raise HTTPException(400, str(exc)) from exc
    righe, totale = await standard_repo.comuni(hazard, f)
    corpo = ogc.pagina(
        righe,
        totale=totale,
        base=_ogc(request),
        id_collezione_=collection_id,
        f=f,
        query=request.url.query,
        adesso=datetime.now(UTC),
    )
    return JSONResponse(corpo, media_type=ogc.GEOJSON)


@router.get(
    "/api/ogc/collections/{collection_id}/items/{feature_id}",
    response_class=JSONResponse,
    summary="OGC API Features: un comune",
)
async def ogc_item(collection_id: str, feature_id: str, request: Request) -> JSONResponse:
    hazard = await _collezione(collection_id)
    riga = await standard_repo.comune(hazard, feature_id)
    if riga is None:
        raise HTTPException(404, "comune sconosciuto")
    corpo = ogc.oggetto(riga, base=_ogc(request), id_collezione_=collection_id)
    return JSONResponse(corpo, media_type=ogc.GEOJSON)
