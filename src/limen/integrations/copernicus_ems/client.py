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

Il pacchetto prodotti pesa ~100 MB per attivazione perché contiene gli
ortofotomosaici; i vettori che ci interessano sono ~20 KB. Si scarica una
volta, si estraggono i soli `observedEventA` nella cache, e lo zip si butta:
i riavvii successivi leggono i vettori e non toccano la rete.
"""

from __future__ import annotations

import io
import re
import shutil
import zipfile
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely import wkt
from shapely.geometry import MultiPolygon
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.dem.zonal import geom_reprojector

log = get_logger(__name__)

_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api"
ACTIVATIONS_URL = f"{_API}/public-activations-info/"
ACTIVATION_DETAIL_URL = f"{_API}/public-activations/"
PRODUCTS_URL = "https://rapidmapping.emergency.copernicus.eu/backend/{code}/{code}_products.zip"

#: Il visore pubblico espone le attivazioni dal 2023. Le precedenti vivono sul
#: sito storico senza un'API documentata, quindi la copertura del catalogo
#: parte da lì — un fatto da riportare nel report, non da nascondere.
CATALOGUE_FROM_YEAR = 2023

#: `event_type` da tenere. Un'attivazione alluvionale mappa anche frane
#: innescate dalla stessa pioggia (`6-Mass Movement`): sono eventi veri ma di
#: un altro pericolo, e infilarli qui gonfierebbe il truth set del flood con
#: celle che non si sono allagate.
FLOOD_EVENT_TYPE = "5-Flood"

#: `notation` da tenere. «Flood trace» è il segno lasciato dall'acqua: quel
#: terreno è stato sotto, quindi conta come positivo quanto «Flooded area».
FLOOD_NOTATIONS = ("Flooded area", "Flood trace")

_OBSERVED_RE = re.compile(r"observedEventA_.*\.(shp|shx|dbf|prj|cpg)$", re.I)
#: `EMSR762_AOI01_DEL_PRODUCT_observedEventA_v1.shp` →  (1, 'DEL', 0)
#: `EMSR762_AOI03_DEL_MONIT01_observedEventA_v2.shp` → (3, 'DEL', 1)
_NAME_RE = re.compile(
    r"^(?P<code>EMSR\d+)_AOI(?P<aoi>\d+)_(?P<ptype>[A-Z]+)_"
    r"(?:PRODUCT|MONIT(?P<monit>\d+))_observedEventA",
    re.I,
)


@dataclass(frozen=True, slots=True)
class Activation:
    code: str
    name: str
    category: str
    event_time: datetime
    countries: tuple[str, ...]
    sub_category: str | None = None


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


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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
    wanted = {c.lower() for c in categories}
    out: list[Activation] = []
    url: str | None = f"{ACTIVATIONS_URL}?limit={page_size}"
    client = await SharedHttpClient.get()
    while url:
        resp = await fetch_with_retry("GET", url, client=client)
        payload = resp.json()
        for row in payload.get("results") or []:
            countries = tuple(str(c) for c in (row.get("countries") or []))
            when = _parse_dt(row.get("eventTime"))
            if country not in countries or when is None:
                continue
            if str(row.get("category", "")).lower() not in wanted:
                continue
            out.append(
                Activation(
                    code=str(row["code"]),
                    name=str(row.get("name") or row["code"]).strip(),
                    category=str(row.get("category") or ""),
                    event_time=when,
                    countries=countries,
                    sub_category=(row.get("subCategory") or None),
                )
            )
        url = payload.get("next")
    out.sort(key=lambda a: a.event_time)
    log.info(
        "ems.activations",
        country=country,
        categories=sorted(wanted),
        found=len(out),
        since_year=CATALOGUE_FROM_YEAR,
    )
    return out


async def fetch_activation_detail(code: str) -> list[dict[str, Any]]:
    """Il dettaglio dell'attivazione: AOI, prodotti, acquisizioni."""
    resp = await fetch_with_retry(
        "GET", f"{ACTIVATION_DETAIL_URL}?code={code}", client=await SharedHttpClient.get()
    )
    results = resp.json().get("results") or []
    return [row for row in results if isinstance(row, dict)]


async def fetch_observation_masks(code: str) -> list[ObservationMask]:
    """Le maschere di osservazione di un'attivazione, una per prodotto.

    Geometria da ``aois[].extent``: verificato su EMSR762 AOI01 che coincide
    con l'``areaOfInterestA`` del pacchetto prodotti (1846,1 km² entrambe),
    quindi non vale scaricare 100 MB per riottenerla.
    """
    out: list[ObservationMask] = []
    for act in await fetch_activation_detail(code):
        for aoi in act.get("aois") or []:
            number = int(aoi.get("number") or 0)
            raw_extent = aoi.get("extent")
            if not raw_extent:
                continue
            try:
                geom = wkt.loads(str(raw_extent))
            except Exception:
                # Un WKT illeggibile è un dato sporco, non un bug nostro: si
                # perde quella maschera e si va avanti.
                log.warning("ems.mask.bad_extent", code=code, aoi=number)
                continue
            for product in aoi.get("products") or []:
                ptype = str(product.get("type") or "").upper()
                monit = int(product.get("monitoringNumber") or 0)
                stamps = [
                    dt
                    for image in product.get("images") or []
                    if (dt := _parse_dt(image.get("acquisitionTime"))) is not None
                ]
                if not stamps:
                    continue
                out.append(
                    ObservationMask(
                        id=f"{code}-aoi{number:02d}-{ptype}{monit}",
                        activation_code=code,
                        aoi_label=f"AOI{number:02d}",
                        product_type=ptype,
                        observed_time=min(stamps),
                        geom=geom,
                    )
                )
    log.info("ems.observation_masks", code=code, masks=len(out))
    return out


async def _acquisition_times(code: str) -> dict[tuple[int, str, int], datetime]:
    """``{(aoi_number, product_type, monitoring_number): earliest acquisition}``.

    L'ora di acquisizione non sta nello shapefile ma nel dettaglio
    dell'attivazione, e serve per distinguerla dall'inizio dell'evento: è
    l'istante in cui il satellite ha visto l'acqua, quindi come ancora del
    preavviso conterebbe ore in cui l'allagamento era già in corso.
    """
    out: dict[tuple[int, str, int], datetime] = {}
    for act in await fetch_activation_detail(code):
        for aoi in act.get("aois") or []:
            number = int(aoi.get("number") or 0)
            for product in aoi.get("products") or []:
                key = (
                    number,
                    str(product.get("type") or "").upper(),
                    int(product.get("monitoringNumber") or 0),
                )
                stamps = [
                    dt
                    for image in product.get("images") or []
                    if (dt := _parse_dt(image.get("acquisitionTime"))) is not None
                ]
                if not stamps:
                    continue
                earliest = min(stamps)
                if key not in out or earliest < out[key]:
                    out[key] = earliest
    return out


def _extract_vectors(archive: Path, dest: Path) -> int:
    """Estrae i soli `observedEventA` dallo zip di zip. Ritorna gli `.shp`."""
    dest.mkdir(parents=True, exist_ok=True)
    found = 0
    with zipfile.ZipFile(archive) as outer:
        for entry in outer.namelist():
            if not entry.lower().endswith(".zip"):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(entry))) as inner:
                for member in inner.namelist():
                    if not _OBSERVED_RE.search(member):
                        continue
                    target = dest / Path(member).name
                    with inner.open(member) as src, target.open("wb") as fh:
                        shutil.copyfileobj(src, fh)
                    if member.lower().endswith(".shp"):
                        found += 1
    return found


async def _ensure_vectors(code: str, *, cache_dir: Path) -> Path | None:
    """Cartella con i vettori dell'attivazione, scaricandoli se assenti."""
    dest = cache_dir / code
    if dest.is_dir() and any(dest.glob("*.shp")):
        log.info("ems.vectors.cache_hit", code=code, path=str(dest))
        return dest

    url = PRODUCTS_URL.format(code=code)
    archive = cache_dir / f"{code}_products.zip"
    cache_dir.mkdir(parents=True, exist_ok=True)
    client = await SharedHttpClient.get()
    try:
        # Streaming: il pacchetto arriva a ~100 MB e tenerlo in memoria non
        # serve a niente, dato che dopo l'estrazione lo cancelliamo.
        async with client.stream("GET", url, follow_redirects=True) as resp:
            resp.raise_for_status()
            with archive.open("wb") as fh:
                async for chunk in resp.aiter_bytes(1 << 20):
                    fh.write(chunk)
    except Exception as exc:
        # Un pacchetto non pubblico (EMSR664 risponde 403) non deve fermare
        # l'ingest degli altri: si registra e si va avanti.
        log.warning("ems.products.unavailable", code=code, url=url, error=str(exc))
        archive.unlink(missing_ok=True)
        return None

    try:
        found = _extract_vectors(archive, dest)
    finally:
        archive.unlink(missing_ok=True)
    if not found:
        log.warning("ems.vectors.none", code=code)
        return None
    log.info("ems.vectors.extracted", code=code, shapefiles=found)
    return dest


def _iter_polygons(geom: BaseGeometry) -> Iterator[BaseGeometry]:
    if isinstance(geom, MultiPolygon):
        yield from geom.geoms
    else:
        yield geom


async def fetch_observed_floods(activation: Activation, *, cache_dir: Path) -> list[ObservedFlood]:
    """I poligoni allagati di un'attivazione, pronti per `flood_events`.

    Import locale di geopandas: la lettura di shapefile serve solo qui e
    all'ingest, non al processo API.
    """
    import geopandas as gpd

    folder = await _ensure_vectors(activation.code, cache_dir=cache_dir)
    if folder is None:
        return []
    acquisitions = await _acquisition_times(activation.code)

    out: list[ObservedFlood] = []
    for shp in sorted(folder.glob("*observedEventA*.shp")):
        match = _NAME_RE.match(shp.name)
        aoi_number = int(match.group("aoi")) if match else 0
        product_type = (match.group("ptype") if match else "DEL").upper()
        monit = int(match.group("monit") or 0) if match else 0
        observed = acquisitions.get((aoi_number, product_type, monit))

        frame = gpd.read_file(shp)
        if frame.empty:
            continue
        if frame.crs is not None and frame.crs.to_epsg() != 4326:
            frame = frame.to_crs(4326)
        # Un trasformatore per file, non uno per poligono: costruirlo dentro
        # il ciclo costa 67 ms a geometria (misurato sui zonali, #104).
        to_metric = geom_reprojector(src_crs=4326, dst_crs=3035)

        for position, (_, row) in enumerate(frame.iterrows()):
            if str(row.get("event_type") or "") != FLOOD_EVENT_TYPE:
                continue
            notation = str(row.get("notation") or "")
            if notation not in FLOOD_NOTATIONS:
                continue
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            for part_index, part in enumerate(_iter_polygons(geom)):
                out.append(
                    ObservedFlood(
                        id=f"{activation.code}-aoi{aoi_number:02d}-{product_type}"
                        f"{monit}-{position}-{part_index}",
                        activation_code=activation.code,
                        aoi_label=f"AOI{aoi_number:02d}",
                        event_time=activation.event_time,
                        observed_time=observed,
                        event_type=str(row.get("obj_desc") or "") or None,
                        detection_method=str(row.get("det_method") or "") or None,
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
                            "product": shp.name,
                        },
                    )
                )
    log.info("ems.observed_floods", code=activation.code, polygons=len(out))
    return out


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
    "FLOOD_EVENT_TYPE",
    "FLOOD_NOTATIONS",
    "Activation",
    "ObservationMask",
    "ObservedFlood",
    "catalogue_provenance",
    "fetch_activation_detail",
    "fetch_activations",
    "fetch_observation_masks",
    "fetch_observed_floods",
]
