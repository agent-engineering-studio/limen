"""Copernicus EMS Rapid Mapping — attivazioni e perimetri allagati osservati (#64).

Il truth set del backtest flood. Il servizio è **pubblico e senza credenziali**,
come EFFIS: le due alternative che l'issue nominava non lo sono o non sono
leggibili da un programma.

* **FloodCat** (il catalogo nazionale della Direttiva Alluvioni) sta su
  `mydewetra.org`, è del Dipartimento di Protezione Civile e richiede
  un'utenza: un client che non si può eseguire non è un client.
* **Polaris (CNR-IRPI)** pubblica rapporti in PDF e schede HTML. Il suo
  WordPress espone `wp-json`, ma i tipi `event` e `report` non sono nella
  REST API, quindi resterebbe da fare screen scraping di un sito di ricerca —
  fragile, e l'issue stessa lo lascia a una issue separata.

Cosa serve dai prodotti EMS, e cosa **non** serve: la geometria di verità è
l'estensione **osservata** (`observedEventA`), non l'area di interesse della
mappatura. Su EMSR762 l'AOI01 misura ~750 km² e l'allagamento 1,19: prendere
l'AOI significherebbe dichiarare allagate centinaia di celle asciutte e
trasformare il FAR in un numero senza senso.

Ogni prodotto pubblica i suoi vettori anche da soli, in GeoJSON (da decine
di KB a 17 MB, ~210 MB tutta l'Italia): non serve il pacchetto prodotti da
~100 MB ad attivazione con gli ortofotomosaici, che per qualche attivazione
risponde 403 mentre i GeoJSON sono aperti (EMSR664, Emilia-Romagna maggio
2023: 6.334 poligoni allagati che lo zip non dava). Verificato su 77 layer di
10 attivazioni: stessi poligoni, nello stesso ordine, quindi gli id di
`flood_events` non cambiano. Elenco, dettaglio e lettura dei layer vengono dal
pacchetto ``copernicus-ems`` (estratto da Limen, Apache-2.0); qui restano il
traffico via ``fetch_with_retry``, la cache su disco e le righe per il DB.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from copernicus_ems import (
    ACTIVATIONS_URL,
    DETAIL_URL,
    FLOOD_EVENT_TYPE,
    FLOOD_NOTATIONS,
    OBSERVED_EVENT,
    Activation,
    EmsError,
    Product,
    activations_url,
    detail_url,
    parse_activations,
    parse_detail,
    parse_layer,
    select_activations,
)
from shapely import wkt
from shapely.geometry import MultiPolygon, shape
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.dem.zonal import geom_reprojector

log = get_logger(__name__)

#: Il visore pubblico espone le attivazioni dal 2023. Le precedenti vivono sul
#: sito storico senza un'API documentata, quindi la copertura del catalogo
#: parte da lì — un fatto da riportare nel report, non da nascondere.
CATALOGUE_FROM_YEAR = 2023


@dataclass(frozen=True, slots=True)
class ObservedFlood:
    """Un poligono di allagamento osservato, con i suoi due tempi."""

    id: str
    activation_code: str
    aoi_label: str
    event_time: datetime
    geom: BaseGeometry
    area_km2: float
    observed_time: datetime | None = None
    event_type: str | None = None
    detection_method: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ObservationMask:
    """Dove il satellite ha guardato, e quando.

    È ciò che rende leggibile il FAR: dentro la maschera l'assenza di un
    poligono allagato è un "non allagato" osservato, fuori non è informazione.
    """

    id: str
    activation_code: str
    aoi_label: str
    product_type: str
    observed_time: datetime
    geom: BaseGeometry
    area_km2: float | None = None


async def fetch_activations(
    *,
    country: str = "Italy",
    categories: Sequence[str] = ("Flood",),
    page_size: int = 500,
) -> list[Activation]:
    """Le attivazioni pubbliche del paese e delle categorie richieste.

    ``categories`` è aperto perché la categoria EMS descrive la *causa*, non
    l'effetto: parecchie alluvioni italiane sono classificate «Storm», e
    scartarle a priori butterebbe via eventi con perimetri allagati regolari.
    """
    tutte: list[Activation] = []
    url: str | None = activations_url(page_size=page_size)
    client = await SharedHttpClient.get()
    while url:
        resp = await fetch_with_retry("GET", url, client=client)
        pagina = parse_activations(resp.content)
        tutte.extend(pagina.activations)
        url = pagina.next_url
    out = select_activations(tutte, country=country, categories=categories)
    log.info(
        "ems.activations",
        country=country,
        categories=sorted(c.lower() for c in categories),
        found=len(out),
        since_year=CATALOGUE_FROM_YEAR,
    )
    return out


async def fetch_products(code: str) -> list[Product]:
    """I prodotti dell'attivazione: AOI, tipo, acquisizioni, layer."""
    resp = await fetch_with_retry("GET", detail_url(code), client=await SharedHttpClient.get())
    return parse_detail(resp.content)


def _mask_id(product: Product) -> str:
    return (
        f"{product.activation_code}-aoi{product.aoi_number:02d}-{product.product_type}"
        f"{product.monitoring_number}"
    )


def _mask(product: Product) -> ObservationMask | None:
    """La maschera di osservazione del prodotto, se ha estensione e immagini.

    Geometria da ``aois[].extent``: verificato su EMSR762 AOI01 che coincide
    con l'``areaOfInterestA`` del pacchetto prodotti (1846,1 km² entrambe).
    """
    if product.aoi_extent_wkt is None or product.observed_time is None:
        return None
    try:
        geom = wkt.loads(product.aoi_extent_wkt)
    except Exception:
        # Un WKT illeggibile è un dato sporco, non un bug nostro: si perde
        # quella maschera e si va avanti.
        log.warning("ems.mask.bad_extent", code=product.activation_code, aoi=product.aoi_number)
        return None
    return ObservationMask(
        id=_mask_id(product),
        activation_code=product.activation_code,
        aoi_label=f"AOI{product.aoi_number:02d}",
        product_type=product.product_type,
        observed_time=product.observed_time,
        geom=geom,
    )


async def _layer(product: Product, *, cache_dir: Path) -> dict[str, Any] | None:
    """Il GeoJSON ``observedEventA`` del prodotto, dalla cache o dalla rete."""
    layer = product.layers.get(OBSERVED_EVENT)
    if layer is None:
        return None
    path = cache_dir / product.activation_code / layer.url.rsplit("/", 1)[-1]
    if path.exists():
        try:
            return parse_layer(path.read_bytes())
        except EmsError:
            # Una cache rovinata si riscarica, non ferma l'ingest.
            log.warning("ems.layer.bad_cache", path=str(path))
            path.unlink()
    try:
        resp = await fetch_with_retry("GET", layer.url, client=await SharedHttpClient.get())
        resp.raise_for_status()
        collection = parse_layer(resp.content)
    except Exception as exc:
        # Un layer non leggibile non deve fermare gli altri prodotti.
        log.warning("ems.layer.unavailable", url=layer.url, error=str(exc)[:200])
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    parziale = path.with_suffix(".part")
    parziale.write_text(json.dumps(collection))
    parziale.rename(path)
    return collection


def _iter_polygons(geom: BaseGeometry) -> Iterator[BaseGeometry]:
    if isinstance(geom, MultiPolygon):
        yield from geom.geoms
    else:
        yield geom


@dataclass(frozen=True, slots=True)
class ActivationTruth:
    """Poligoni allagati e maschere di un'attivazione, dallo stesso dettaglio."""

    floods: list[ObservedFlood]
    masks: list[ObservationMask]
    #: Maschere di prodotti che il dettaglio dice **senza** layer osservato
    #: (mai consegnati): se un ingest precedente le ha scritte, vanno tolte.
    #: Un layer elencato ma non scaricato (403, 5xx) non è qui: è un errore
    #: transitorio, e la maschera di prima resta con i suoi poligoni.
    absent_masks: list[str] = field(default_factory=list)


async def fetch_activation_truth(activation: Activation, *, cache_dir: Path) -> ActivationTruth:
    """I poligoni allagati e le maschere di osservazione di un'attivazione.

    Una maschera dice «qui il satellite ha guardato»: dentro, l'assenza di un
    poligono è un *non allagato* osservato. Per questo si scrive **solo per i
    prodotti il cui layer osservato è stato letto**: con il layer perso (403,
    5xx, corpo illeggibile) o assente (prodotto annullato) la maschera direbbe
    asciutto un posto di cui non si sa niente, e il backtest conterebbe falsi
    allarmi dove manca il dato — «non misurato» letto come «nessun pericolo».

    L'id del poligono porta la posizione della feature **nel layer intero**,
    prima del filtro: è la stessa posizione che aveva nello shapefile del
    pacchetto, e tenerla fissa è ciò che rende l'upsert idempotente.

    Il dettaglio si chiede una volta; se non risponde, l'attivazione resta
    vuota in entrambe le liste.
    """
    try:
        products = await fetch_products(activation.code)
    except Exception as exc:
        log.warning("ems.detail.unavailable", code=activation.code, error=str(exc)[:200])
        return ActivationTruth(floods=[], masks=[])
    # Un trasformatore per attivazione, non uno per poligono: costruirlo
    # dentro il ciclo costa 67 ms a geometria (misurato sui zonali, #104).
    to_metric = geom_reprojector(src_crs=4326, dst_crs=3035)
    floods: list[ObservedFlood] = []
    masks: list[ObservationMask] = []
    absent: list[str] = []
    for product in products:
        if OBSERVED_EVENT not in product.layers:
            absent.append(_mask_id(product))
            continue
        collection = await _layer(product, cache_dir=cache_dir)
        if collection is None:
            continue
        mask = _mask(product)
        if mask is not None:
            masks.append(mask)
        tag = f"{product.product_type}{product.monitoring_number}"
        source = product.layers[OBSERVED_EVENT].url.rsplit("/", 1)[-1]
        for position, feature in enumerate(collection["features"]):
            props = feature.get("properties") or {}
            if props.get("event_type") != FLOOD_EVENT_TYPE:
                continue
            notation = str(props.get("notation") or "")
            if notation not in FLOOD_NOTATIONS or feature.get("geometry") is None:
                continue
            geom = shape(feature["geometry"])
            if geom.is_empty:
                continue
            for part_index, part in enumerate(_iter_polygons(geom)):
                floods.append(
                    ObservedFlood(
                        id=f"{activation.code}-aoi{product.aoi_number:02d}-{tag}"
                        f"-{position}-{part_index}",
                        activation_code=activation.code,
                        aoi_label=f"AOI{product.aoi_number:02d}",
                        event_time=activation.event_time,
                        observed_time=product.observed_time,
                        event_type=str(props.get("obj_desc") or "") or None,
                        detection_method=str(props.get("det_method") or "") or None,
                        # Per parte e non per riga: una MultiPolygon diventa
                        # più righe, e ripetere l'area del gruppo su ognuna
                        # conterebbe lo stesso allagamento N volte nei totali.
                        area_km2=float(to_metric(part).area) / 1e6,
                        geom=part,
                        attributes={
                            "notation": notation,
                            "activation_name": activation.name,
                            "category": activation.category,
                            "sub_category": activation.sub_category,
                            "product": source,
                        },
                    )
                )
    log.info("ems.activation_truth", code=activation.code, polygons=len(floods), masks=len(masks))
    return ActivationTruth(floods=floods, masks=masks, absent_masks=absent)


def catalogue_provenance() -> dict[str, str]:
    """Provenienza da scrivere nel report: fonte, licenza, limiti.

    Solo fatti che non dipendono da cosa è stato ingerito. I conteggi stanno
    in ``activations_summary()``, che li legge dal database: tenerli qui
    voleva dire passare una lista vuota quando il chiamante non l'aveva, e
    stampare "0 attivazioni" accanto a un catalogo pieno.
    """
    return {
        "source": "Copernicus Emergency Management Service — Rapid Mapping",
        "licence": "© European Union, Copernicus EMS. Free to use with attribution.",
        "api": ACTIVATIONS_URL,
        "credentials": "none",
        "coverage_note": (
            f"Il visore pubblico espone le attivazioni dal {CATALOGUE_FROM_YEAR}; "
            "quelle precedenti non hanno un'API documentata."
        ),
        "geometry": "observedEventA (estensione osservata), non areaOfInterest",
        "known_limit": (
            "La delineazione satellitare è un limite inferiore: allagamenti "
            "urbani brevi o sotto chioma possono non comparire, quindi un "
            "falso allarme misurato qui può essere un evento non visto."
        ),
    }


__all__ = [
    "ACTIVATIONS_URL",
    "CATALOGUE_FROM_YEAR",
    "DETAIL_URL",
    "FLOOD_EVENT_TYPE",
    "FLOOD_NOTATIONS",
    "Activation",
    "ActivationTruth",
    "EmsError",
    "ObservationMask",
    "ObservedFlood",
    "catalogue_provenance",
    "fetch_activation_truth",
    "fetch_activations",
    "fetch_products",
]
