"""OGC API Features, classi Core e GeoJSON (#503): i punteggi per comune.

Una collezione per pericolo, ``comuni-<pericolo>``: un oggetto per comune con
la classe peggiore, il punteggio massimo e quante celle sono sopra soglia —
la stessa riga di ``mv_comune_risk`` che leggono la classifica e il CAP. Basta
a QGIS, a ``ogrinfo`` e a un geoportale per aprire Limen senza un client
scritto apposta. Le celle (312.550) restano sulle tile vettoriali: una
collezione da un oggetto per km² servita a pagine non è quello che un
geoportale vuole.

Qui solo i documenti: il parsing dei parametri e le risposte JSON, senza
database. Le geometrie arrivano già semplificate dal repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.core.models.hazard import HazardType
from limen.core.standard.cap import attribuzione_copernicus

CONFORMITA = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
]
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
GEOJSON = "application/geo+json"
#: Il riquadro dell'Italia, l'estensione dichiarata delle collezioni.
ITALIA = (6.6, 35.4, 18.6, 47.1)
LIMITE_DEFAULT = 10
LIMITE_MASSIMO = 1000
_NOME = {
    HazardType.LANDSLIDE: "frane",
    HazardType.FLOOD: "alluvioni",
    HazardType.WILDFIRE: "incendi boschivi",
}
_AVVERTENZA = (
    "Limen non è un sistema di allertamento ufficiale: i punteggi sono uno strumento di "
    "supporto alle decisioni e non sostituiscono la Protezione civile."
)


class ParametroNonValidoError(ValueError):
    """Un parametro della richiesta non rispetta la specifica: risposta 400."""


@dataclass(frozen=True, slots=True)
class Filtro:
    bbox: tuple[float, float, float, float] | None
    dal: datetime | None
    al: datetime | None
    limit: int
    offset: int


def id_collezione(hazard: HazardType) -> str:
    return f"comuni-{hazard.value}"


def da_id_collezione(id_: str) -> HazardType | None:
    if not id_.startswith("comuni-"):
        return None
    try:
        return HazardType(id_.removeprefix("comuni-"))
    except ValueError:
        return None


def leggi_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    try:
        v = [float(x) for x in raw.split(",")]
    except ValueError as exc:
        raise ParametroNonValidoError("bbox: quattro numeri separati da virgola") from exc
    if len(v) != 4 or v[0] > v[2] or v[1] > v[3]:
        raise ParametroNonValidoError("bbox: minx,miny,maxx,maxy in CRS84")
    return v[0], v[1], v[2], v[3]


def _istante(s: str) -> datetime | None:
    if s in ("", ".."):
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ParametroNonValidoError(f"datetime: {s!r} non è RFC 3339") from exc
    if t.tzinfo is None:
        raise ParametroNonValidoError("datetime: serve il fuso")
    return t


def leggi_datetime(raw: str | None) -> tuple[datetime | None, datetime | None]:
    """Un istante, o un intervallo ``a/b`` con ``..`` per un estremo aperto."""
    if raw is None:
        return None, None
    if "/" in raw:
        a, b = raw.split("/", 1)
        return _istante(a), _istante(b)
    t = _istante(raw)
    if t is None:
        raise ParametroNonValidoError("datetime: un istante non può essere aperto")
    return t, t


def filtro(
    *, bbox: str | None, datetime_: str | None, limit: int | None, offset: int | None
) -> Filtro:
    dal, al = leggi_datetime(datetime_)
    n = LIMITE_DEFAULT if limit is None else limit
    if n < 1:
        raise ParametroNonValidoError("limit: almeno 1")
    if offset is not None and offset < 0:
        raise ParametroNonValidoError("offset: non negativo")
    return Filtro(
        bbox=leggi_bbox(bbox),
        dal=dal,
        al=al,
        # La specifica chiede di ridurre un limit troppo alto, non di rifiutarlo.
        limit=min(n, LIMITE_MASSIMO),
        offset=offset or 0,
    )


def _link(href: str, rel: str, type_: str, title: str | None = None) -> dict[str, str]:
    out = {"href": href, "rel": rel, "type": type_}
    if title:
        out["title"] = title
    return out


def landing(base: str) -> dict[str, Any]:
    return {
        "title": "Limen — OGC API Features",
        "description": "Il pericolo di frane, alluvioni e incendi boschivi per comune. "
        + _AVVERTENZA,
        "links": [
            _link(f"{base}", "self", "application/json"),
            _link(f"{base}/conformance", "conformance", "application/json"),
            _link(f"{base}/collections", "data", "application/json"),
            _link(
                base.removesuffix("/api/ogc") + "/openapi.json",
                "service-desc",
                "application/vnd.oai.openapi+json;version=3.0",
            ),
        ],
    }


def collezione(base: str, hazard: HazardType, *, anno: int) -> dict[str, Any]:
    id_ = id_collezione(hazard)
    descrizione = (
        f"Pericolo di {_NOME[hazard]} per comune, dall'ultimo calcolo orario: classe peggiore, "
        "punteggio massimo (0-1) e celle da 1 km² sopra soglia. " + _AVVERTENZA
    )
    attribuzione = "Limen (EUPL-1.2)"
    if hazard is HazardType.FLOOD:
        attribuzione += ". " + attribuzione_copernicus(anno)
        descrizione += " " + attribuzione_copernicus(anno)
    return {
        "id": id_,
        "title": f"Comuni — {_NOME[hazard]}",
        "description": descrizione,
        "attribution": attribuzione,
        "itemType": "feature",
        "crs": [CRS84],
        "extent": {"spatial": {"bbox": [list(ITALIA)], "crs": CRS84}},
        "links": [
            _link(f"{base}/collections/{id_}", "self", "application/json"),
            _link(f"{base}/collections/{id_}/items", "items", GEOJSON),
        ],
    }


def collezioni(base: str, hazards: list[HazardType], *, anno: int) -> dict[str, Any]:
    return {
        "links": [_link(f"{base}/collections", "self", "application/json")],
        "collections": [collezione(base, h, anno=anno) for h in hazards],
    }


def oggetto(riga: dict[str, Any], *, base: str, id_collezione_: str) -> dict[str, Any]:
    props = {k: v for k, v in riga.items() if k != "geometry"}
    if isinstance(props.get("computed_at"), datetime):
        props["computed_at"] = props["computed_at"].isoformat()
    return {
        "type": "Feature",
        "id": riga["istat_code"],
        "geometry": riga["geometry"],
        "properties": props,
        "links": [
            _link(
                f"{base}/collections/{id_collezione_}/items/{riga['istat_code']}",
                "self",
                GEOJSON,
            ),
            _link(f"{base}/collections/{id_collezione_}", "collection", "application/json"),
        ],
    }


def pagina(
    righe: list[dict[str, Any]],
    *,
    totale: int,
    base: str,
    id_collezione_: str,
    f: Filtro,
    query: str,
    adesso: datetime,
) -> dict[str, Any]:
    url = f"{base}/collections/{id_collezione_}/items"
    links = [_link(f"{url}?{query}" if query else url, "self", GEOJSON)]
    if f.offset + len(righe) < totale:
        parti = [p for p in query.split("&") if p and not p.startswith(("offset=", "limit="))]
        parti += [f"limit={f.limit}", f"offset={f.offset + f.limit}"]
        links.append(_link(f"{url}?{'&'.join(parti)}", "next", GEOJSON))
    return {
        "type": "FeatureCollection",
        "features": [oggetto(r, base=base, id_collezione_=id_collezione_) for r in righe],
        "numberMatched": totale,
        "numberReturned": len(righe),
        "timeStamp": adesso.isoformat(),
        "links": links,
    }
