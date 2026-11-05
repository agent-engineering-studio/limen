"""INGV ingestion job: events + optional ShakeMap raster bytes.

Orchestrates :class:`IngvHttpClient` and writes to:

* ``seismic_events`` (per event)
* ``raster_refs`` + ``ObjectStore`` (per event with a ShakeMap)
* ``seismic_pga_cella`` (per event, the cells it shook)

Idempotent: events are upserted by INGV ``eventID``; the ShakeMap path
written into the ObjectStore is deterministic, so re-running overwrites
the same key.

**Una ShakeMap si riscarica quando cambia versione**, non per un tempo fisso.
Prima valeva «stabile dopo 24 ore»; la Mw 5.5 del Tirreno meridionale del
23 ottobre 2026 ha avuto quattro versioni, l'ultima quaranta ore dopo, e
quella regola la perdeva. Ogni giro legge ``info.json`` (pochi kB) e scarica
i 10-12 MB di ``grid.xml`` solo se la versione è diversa da quella salvata in
``seismic_events.attributes.shakemap_version``. Le 24 ore restano il ripiego
quando ``info.json`` non si legge.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from shapely.geometry import Point, box

from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.object_store import ObjectStore, build_object_store
from limen.data.repos.raster_refs_repo import sha256_hex
from limen.data.repos.raster_refs_repo import upsert as upsert_raster_ref
from limen.data.repos.seismic_repo import (
    SeismicEvent,
    celle_nel_riquadro,
    count_events,
    get_event,
    pga_celle_calcolata,
    salva_pga_celle,
    ultima_cella_creata,
    upsert_event,
)
from limen.integrations.ingv.shakemap_client import IngvHttpClient
from limen.integrations.ingv.shakemap_grid import (
    GrigliaNonValidaError,
    celle_scosse,
    leggi_griglia,
)

if TYPE_CHECKING:
    from ingv_shakemap import Event, ShakeMapInfo

log = get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_MIN_MAGNITUDE = 3.5
#: Solo se ``info.json`` non si legge: oltre questo, una mappa già calcolata
#: non si riscarica alla cieca.
_SHAKEMAP_STABILE_DOPO = timedelta(hours=24)
#: Le chiavi di ``seismic_events.attributes`` scritte da questo job, non da INGV.
VERSIONE = "shakemap_version"
STATO = "shakemap_status"


async def _pga_per_cella(event_id: str, grid_bytes: bytes, pga_min_g: float) -> int:
    """Lo scuotimento della ShakeMap sulle celle della griglia, sopra la soglia."""
    try:
        # Fino a 12 MB di testo: fuori dal loop, che è lo stesso dello sweep.
        griglia = await asyncio.to_thread(leggi_griglia, grid_bytes)
    except GrigliaNonValidaError as exc:
        log.warning("ingv.shakemap.illeggibile", event_id=event_id, error=str(exc))
        return 0
    celle = await celle_nel_riquadro(*griglia.bbox)
    salvate = await salva_pga_celle(event_id, celle_scosse(griglia, celle, pga_min_g))
    log.info("ingv.shakemap.celle", event_id=event_id, celle=salvate, pga_min_g=pga_min_g)
    return salvate


def _shakemap_key(event_id: str) -> str:
    """Deterministic ObjectStore key for the ShakeMap of a given event."""
    return f"shakemap/{event_id}/grid.xml"


def evento_limen(ev: Event, *, attributi: dict[str, Any] | None = None) -> SeismicEvent:
    """Un evento del catalogo (già letto da ``ingv-shakemap``) come riga di Limen."""
    return SeismicEvent(
        id=ev.id,
        origin_time=ev.time,
        magnitude=ev.magnitude,
        magnitude_type=ev.magnitude_type,
        depth_km=ev.depth_km,
        geom=Point(ev.longitude, ev.latitude),
        region=ev.place,
        attributes={**ev.properties, **(attributi or {})},
    )


def _attributi_mappa(info: ShakeMapInfo | None) -> dict[str, Any]:
    if info is None:
        return {}
    return {VERSIONE: info.version, STATO: info.map_status}


def _attributi_salvati(precedente: SeismicEvent | None) -> dict[str, Any]:
    attributi = {} if precedente is None else (precedente.attributes or {})
    return {k: attributi[k] for k in (VERSIONE, STATO) if k in attributi}


def _invariata(precedente: SeismicEvent, info: ShakeMapInfo | None, *, eta: timedelta) -> bool:
    """Se la ShakeMap già calcolata è ancora quella di INGV."""
    if info is None:
        return eta > _SHAKEMAP_STABILE_DOPO
    salvata = (precedente.attributes or {}).get(VERSIONE)
    return info.version is not None and info.version == salvata


async def run_ingv_sync(
    *,
    bbox: tuple[float, float, float, float],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_magnitude: float = DEFAULT_MIN_MAGNITUDE,
    client: IngvHttpClient | None = None,
    object_store: ObjectStore | None = None,
) -> dict[str, int]:
    """Fetch events for the trailing ``lookback_days`` and upsert them.

    For events with a published ShakeMap, fetch ``grid.xml`` when its version
    changed, write it to the object store, create a :func:`raster_refs.upsert`
    row that the event row points at via ``raster_ref_id``, and store the PGA
    of every cell it shook.

    Returns ``{"events": n, "shakemaps": k, "celle": c, "invariate": u}``.
    """
    cli = client or IngvHttpClient()
    store = object_store or build_object_store()

    end = datetime.now(UTC)
    start = end - timedelta(days=lookback_days)

    eventi = await cli.fetch_events(bbox=bbox, start=start, end=end, min_magnitude=min_magnitude)
    log.info("ingv.sync.features", count=len(eventi))

    events = 0
    shakemaps = 0
    celle = 0
    invariate = 0
    bbox_geom = box(*bbox)
    pga_min_g = load_regional_thresholds().seismic.pga_min_g
    # Codex, #288: celle nate dopo il calcolo (una regione aggiunta) vogliono
    # la loro PGA anche da un evento già vecchio.
    ultima_cella = await ultima_cella_creata()

    for ev in eventi:
        info = await cli.fetch_info(ev.id)
        precedente = await get_event(ev.id)
        if (
            precedente is not None
            and precedente.shakemap_path is not None
            and await pga_celle_calcolata(ev.id, dopo=ultima_cella)
            and _invariata(precedente, info, eta=end - ev.time)
        ):
            # Si tiene la versione salvata: è quella delle righe per cella.
            await upsert_event(evento_limen(ev, attributi=_attributi_salvati(precedente)))
            events += 1
            invariate += 1
            continue

        grid_bytes = await cli.fetch_shakemap_grid(ev.id)
        # La versione nuova si scrive solo con la griglia in mano: scritta
        # senza, il giro dopo la crederebbe già calcolata e le righe per cella
        # resterebbero quelle della versione vecchia.
        event = evento_limen(
            ev,
            attributi=_attributi_mappa(info) if grid_bytes else _attributi_salvati(precedente),
        )
        if grid_bytes:
            key = _shakemap_key(ev.id)
            location = await store.put(key, grid_bytes, content_type="application/xml")
            ref_id = await upsert_raster_ref(
                kind="shakemap_grid",
                path=key,
                bbox=bbox_geom,
                crs="EPSG:4326",
                checksum_sha256=sha256_hex(grid_bytes),
                size_bytes=len(grid_bytes),
                metadata={
                    "event_id": ev.id,
                    "magnitude": ev.magnitude,
                    "object_store_location": location,
                    VERSIONE: None if info is None else info.version,
                },
            )
            shakemaps += 1
            log.info(
                "ingv.shakemap.stored",
                event_id=ev.id,
                key=key,
                ref_id=ref_id,
                versione=None if info is None else info.version,
                stato=None if info is None else info.map_status,
            )
            event = SeismicEvent(
                id=event.id,
                origin_time=event.origin_time,
                magnitude=event.magnitude,
                magnitude_type=event.magnitude_type,
                depth_km=event.depth_km,
                geom=event.geom,
                region=event.region,
                shakemap_path=key,
                raster_ref_id=ref_id,
                dataset_version_id=event.dataset_version_id,
                attributes=event.attributes,
            )

        await upsert_event(event)
        events += 1
        if grid_bytes:
            # Dopo l'evento: le righe per cella hanno la chiave verso di lui.
            celle += await _pga_per_cella(ev.id, grid_bytes, pga_min_g)

    total_after = await count_events()
    log.info(
        "ingv.sync.done",
        events=events,
        shakemaps=shakemaps,
        celle=celle,
        invariate=invariate,
        total=total_after,
    )
    return {"events": events, "shakemaps": shakemaps, "celle": celle, "invariate": invariate}
