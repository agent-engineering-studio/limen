"""``limen ingest-events [--hazard landslide|flood]`` — cataloghi datati.

Il truth set contro cui i backtest §2.5 rigiocano la storia. Un pericolo per
sorgente, perché le due sorgenti non si somigliano affatto:

* ``--hazard landslide`` (default) — ITALICA / e-ITALICA: un CSV di **punti**
  datati, scaricabile da un DOI Zenodo fissato. IFFI da solo è un inventario
  senza date.
* ``--hazard flood`` — Copernicus EMS Rapid Mapping: i **poligoni** di
  estensione allagata osservata delle attivazioni italiane. Un allagamento ha
  un'estensione, e su celle da 1 km² il perimetro è ciò che rende il backtest
  misurabile invece di indicativo (#64).

Entrambi idempotenti: l'upsert è per id di catalogo e i download sono in
cache, quindi rieseguire il comando non riscrive nulla e non riscarica nulla.

Source resolution (for reproducible init on a fresh machine):
1. ``LIMEN_ITALICA_CSV`` — explicit local path wins (offline / custom file);
2. otherwise download e-ITALICA v4 from the pinned Zenodo DOI
   (10.5281/zenodo.14204473, CC-BY-4.0) into ``LIMEN_DATA_DIR`` and cache it.

Idempotent: the download is skipped when the cached file already exists, and
the upsert is keyed by catalogue id.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import Point

from limen.cli.bootstrap_static import FORCE_ENV
from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import dataset_versions_repo, flood_events_repo
from limen.data.repos.landslide_events_repo import LandslideEvent, count_events
from limen.data.repos.landslide_events_repo import upsert_many as events_upsert
from limen.integrations._http import SharedHttpClient, fetch_with_retry
from limen.integrations.copernicus_ems.client import (
    ObservationMask,
    ObservedFlood,
    catalogue_provenance,
    fetch_activation_truth,
    fetch_activations,
)

log = get_logger(__name__)

# Pinned e-ITALICA v4 (Zenodo DOI 10.5281/zenodo.14204473, CC-BY-4.0).
# The download lives under the /api/records/ path — the bare /records/ path
# returns 404 for the /content file endpoint.
_ITALICA_URL = "https://zenodo.org/api/records/14204473/files/ITALICA_v4.csv/content"
_ITALICA_FILENAME = "ITALICA_v4.csv"


async def _resolve_csv() -> Path | None:
    """Return the ITALICA CSV path, downloading from Zenodo if not local."""
    explicit = os.getenv("LIMEN_ITALICA_CSV", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            log.error("ingest_events.csv_missing", path=str(path))
            return None
        return path

    data_dir = Path(os.getenv("LIMEN_DATA_DIR", "./data")).expanduser()
    dest = data_dir / _ITALICA_FILENAME
    if dest.is_file() and dest.stat().st_size > 0:
        log.info("ingest_events.cache_hit", path=str(dest))
        return dest

    url = os.getenv("LIMEN_ITALICA_URL", _ITALICA_URL)
    log.info("ingest_events.download", url=url, dest=str(dest))
    resp = await fetch_with_retry("GET", url, client=await SharedHttpClient.get())
    data_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    log.info("ingest_events.downloaded", path=str(dest), bytes=len(resp.content))
    return dest


def _f(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_utc(raw: str | None) -> datetime | None:
    """Parse ITALICA ``utc_date`` (``DD/MM/YYYY HH:MM`` or ``DD/MM/YYYY``)."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_rows(path: Path) -> list[LandslideEvent]:
    events: list[LandslideEvent] = []
    skipped = 0
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            rid = (row.get("id") or "").strip()
            lon = _f(row.get("lon"))
            lat = _f(row.get("lat"))
            when = _parse_utc(row.get("utc_date"))
            if not rid or lon is None or lat is None or when is None:
                skipped += 1
                continue
            events.append(
                LandslideEvent(
                    id=rid,
                    source=(row.get("information_source") or "").strip() or "unknown",
                    event_time=when,
                    geom=Point(lon, lat),
                    temporal_accuracy=(row.get("temporal_accuracy") or "").strip() or None,
                    geographic_accuracy=(row.get("geographic_accuracy") or "").strip() or None,
                    landslide_type=(row.get("landslide_type") or "").strip() or None,
                    region=(row.get("region") or "").strip() or None,
                    province=(row.get("province") or "").strip() or None,
                    municipality=(row.get("municipality") or "").strip() or None,
                    elevation_m=_f(row.get("elevation")),
                    slope_deg=_f(row.get("slope")),
                    duration_h=_f(row.get("duration")),
                    cumulated_rainfall_mm=_f(row.get("cumulated_rainfall")),
                    attributes={"catalogue": "italica", "land_cover": row.get("land_cover")},
                )
            )
    if skipped:
        log.warning("ingest_events.rows_skipped", skipped=skipped, note="missing id/lon/lat/date")
    return events


async def _run_landslide() -> int:
    try:
        path = await _resolve_csv()
    finally:
        await SharedHttpClient.aclose()
    if path is None:
        return 1

    events = _parse_rows(path)
    log.info("ingest_events.parsed", path=str(path), events=len(events))

    async with lifespan_pool():
        await run_migrations()
        n = await events_upsert(events)
        total = await count_events()
    log.info("ingest_events.done", hazard="landslide", upserted=n, total_in_db=total)
    return 0


def _flood_categories() -> tuple[str, ...]:
    """Categorie EMS da ingerire.

    Default ``Flood,Storm``: la categoria EMS descrive la *causa* e diverse
    alluvioni italiane sono catalogate «Storm» (EMSR928 Lombardia, EMSR930
    Basilicata). Il filtro sui poligoni resta comunque `5-Flood`, quindi
    allargare la categoria non fa entrare eventi di un altro pericolo — fa
    solo guardare in più pacchetti.
    """
    raw = os.getenv("LIMEN_FLOOD_EVENTS_CATEGORIES", "Flood,Storm")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


#: La riga di ``dataset_versions`` del catalogo EMS: la stessa per il comando
#: e per il passo notturno, così una notte senza attivazioni nuove non riscrive
#: le migliaia di poligoni già in ``flood_events``.
EMS_SOURCE = "copernicus-ems"
EMS_DATASET = "flood_events"


#: Da aumentare quando cambia come si leggono i layer (notazioni, attributi,
#: area, poligoni superati): il contenuto in ingresso sarebbe lo stesso, le
#: righe scritte no.
VERSIONE_CALCOLO = 2


def _riga(**campi: object) -> str:
    return json.dumps(campi, sort_keys=True, separators=(",", ":"), default=str)


def _versione(
    polygons: list[ObservedFlood], masks: list[ObservationMask], absent: list[str]
) -> str:
    """SHA-256 di **tutto** ciò che le due upsert scrivono, in JSON canonico.

    Non solo id e geometria: una correzione EMS dell'``eventTime``, o un
    attributo letto diversamente, lascia uguali gli id e cambia le righe.
    """
    righe = [f"v{VERSIONE_CALCOLO}"]
    righe += [
        _riga(
            id=p.id,
            activation_code=p.activation_code,
            aoi_label=p.aoi_label,
            event_time=p.event_time,
            observed_time=p.observed_time,
            event_type=p.event_type,
            detection_method=p.detection_method,
            area_km2=p.area_km2,
            attributes=p.attributes,
            geom=p.geom.wkb_hex,
        )
        for p in sorted(polygons, key=lambda x: x.id)
    ]
    righe += [
        _riga(
            id=m.id,
            activation_code=m.activation_code,
            aoi_label=m.aoi_label,
            product_type=m.product_type,
            observed_time=m.observed_time,
            area_km2=m.area_km2,
            geom=m.geom.wkb_hex,
        )
        for m in sorted(masks, key=lambda x: x.id)
    ]
    righe.append(_riga(absent=sorted(absent)))
    return dataset_versions_repo.content_hash(righe)


async def sincronizza_alluvioni(*, forzato: bool = False) -> dict[str, Any]:
    """Attivazioni EMS italiane → ``flood_events``. Pool già aperto, client condiviso
    lasciato aperto: lo chiamano sia il comando sia il passo notturno del worker.

    ``esito``: ``scritto`` o ``invariato`` (stesso contenuto della volta prima,
    niente scritture; ``forzato`` scrive lo stesso). Nessun poligono letto
    **solleva**: è una sorgente che non ha risposto, e la riga di ``job_runs``
    deve dirlo invece di restare verde per settimane. Nessuna attivazione, o
    attivazioni di cui non si è letto il dettaglio, danno ``status: warn``.
    """
    dove = os.getenv("LIMEN_FLOOD_EVENTS_CACHE")
    cache = Path(dove).expanduser() if dove else radice_dati() / "flood_events"
    country = os.getenv("LIMEN_FLOOD_EVENTS_COUNTRY", "Italy")

    activations = await fetch_activations(country=country, categories=_flood_categories())
    if not activations:
        # Nessuna attivazione è un risultato possibile e non un errore:
        # un paese senza alluvioni mappate nella finestra pubblica.
        log.warning("ingest_events.flood.no_activations", country=country)
        return {"esito": "nessuna_attivazione", "attivazioni": 0, "status": "warn"}
    polygons: list[ObservedFlood] = []
    masks: list[ObservationMask] = []
    absent: list[str] = []
    letti: list[str] = []
    senza_dettaglio = 0
    for activation in activations:
        # Una maschera senza poligoni è un'osservazione «asciutto» solo se
        # il layer è stato letto: lo decide fetch_activation_truth, che
        # restituisce le due cose dallo stesso dettaglio.
        truth = await fetch_activation_truth(activation, cache_dir=cache)
        if not (truth.floods or truth.masks or truth.absent_masks):
            # Dettaglio o layer non letti: un'attivazione letta ha almeno una
            # maschera, anche quando non ha visto acqua.
            senza_dettaglio += 1
        polygons.extend(truth.floods)
        masks.extend(truth.masks)
        absent.extend(truth.absent_masks)
        letti.extend(truth.prodotti_letti)

    log.info(
        "ingest_events.flood.parsed",
        polygons=len(polygons),
        activations=len(activations),
        years=sorted({a.event_time.year for a in activations}),
    )
    conti: dict[str, Any] = {
        "attivazioni": len(activations),
        "poligoni": len(polygons),
        "maschere": len(masks),
        "senza_dettaglio": senza_dettaglio,
    }
    if senza_dettaglio:
        conti["status"] = "warn"
    if not polygons:
        raise RuntimeError(
            f"Copernicus EMS: nessun poligono da {len(activations)} attivazioni "
            f"({senza_dettaglio} senza dettaglio)"
        )

    versione = _versione(polygons, masks, absent)
    if not forzato and await dataset_versions_repo.find(EMS_SOURCE, EMS_DATASET, versione):
        log.info("ingest_events.flood.unchanged", version=versione[:12])
        return {"esito": "invariato", **conti}

    n = await flood_events_repo.upsert_many(polygons)
    tolti = await flood_events_repo.togli_superati(letti, tenuti=[p.id for p in polygons])
    m, tolte = await flood_events_repo.upsert_masks(masks, absent=absent)
    total = await flood_events_repo.count_events()
    provenance = catalogue_provenance()
    await dataset_versions_repo.record(
        source=EMS_SOURCE,
        dataset=EMS_DATASET,
        version=versione,
        metadata={**conti, "licence": provenance["licence"]},
    )
    log.info(
        "ingest_events.done",
        hazard="flood",
        upserted=n,
        removed=tolti,
        masks=m,
        masks_removed=tolte,
        total_in_db=total,
        source=provenance["source"],
        licence=provenance["licence"],
    )
    return {
        "esito": "scritto",
        **conti,
        "poligoni_tolti": tolti,
        "maschere_tolte": tolte,
        "totale": total,
    }


async def _run_flood() -> int:
    forzato = os.environ.get(FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}
    try:
        async with lifespan_pool():
            await run_migrations()
            await sincronizza_alluvioni(forzato=forzato)
    except RuntimeError as exc:
        log.error("ingest_events.flood.failed", error=str(exc))
        return 1
    finally:
        await SharedHttpClient.aclose()
    return 0


async def run(hazard: str = "landslide") -> int:
    """Dispatcher per pericolo."""
    if hazard == "flood":
        return await _run_flood()
    if hazard in ("landslide", ""):
        return await _run_landslide()
    log.error("ingest_events.unknown_hazard", hazard=hazard)
    return 2


def main() -> int:
    import asyncio

    return asyncio.run(run(os.getenv("LIMEN_INGEST_HAZARD", "landslide")))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
