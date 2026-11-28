"""EFFIS ingestion job: fetch burnt-area perimeters and upsert."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from effis_client import perimeter_attributes
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from limen.core.logging import get_logger
from limen.data.object_store import ObjectStore, build_object_store
from limen.data.repos.fire_repo import (
    PERIMETER_LAYER,
    FirePerimeter,
    count_perimeters,
    upsert_perimeter,
)
from limen.data.repos.raster_refs_repo import (
    sha256_hex,
)
from limen.data.repos.raster_refs_repo import (
    upsert as upsert_raster_ref,
)
from limen.integrations.effis.fire_client import EffisHttpClient

log = get_logger(__name__)

DEFAULT_LOOKBACK_DAYS = 90


def _coerce_multipolygon(geom: BaseGeometry) -> MultiPolygon | None:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    # Fix invalid geometries (self-intersections etc.) and retry.
    fixed = make_valid(geom)
    if isinstance(fixed, MultiPolygon):
        return fixed
    if isinstance(fixed, Polygon):
        return MultiPolygon([fixed])
    return None


def _parse_feature(feat: dict[str, Any], *, layer: str = PERIMETER_LAYER) -> FirePerimeter | None:
    """Un perimetro EFFIS come riga di `fire_perimeters`, con il suo layer.

    Id, giorno, ettari, Comune, uso del suolo e revisione li legge
    `effis_client.perimeter_attributes`, da qualunque campo il layer usi.
    Qui resta la geometria, che Limen salva come MultiPolygon valido.
    """
    attributes = perimeter_attributes(feat)
    if attributes.id is None:
        log.warning("effis.feature.skip", reason="no id")
        return None
    feat_id = attributes.id

    geom_field = feat.get("geometry")
    if geom_field is None:
        log.warning("effis.feature.skip", reason="no geometry", feat_id=feat_id)
        return None
    try:
        shapely_geom = shape(geom_field)
    except (ValueError, TypeError) as e:
        log.warning("effis.feature.skip", reason=f"bad geometry: {e}", feat_id=feat_id)
        return None

    multi = _coerce_multipolygon(shapely_geom)
    if multi is None:
        log.warning("effis.feature.skip", reason="non-polygon geometry", feat_id=feat_id)
        return None

    if attributes.fire_date is None:
        log.warning("effis.feature.no_date", feat_id=feat_id)

    return FirePerimeter(
        id=feat_id,
        fire_date=attributes.fire_date,
        area_ha=attributes.area_ha,
        country=attributes.country,
        province=attributes.province,
        geom=multi,
        layer=layer,
        attributes=dict(feat.get("properties") or {}),
        municipality=attributes.municipality,
        final_date=attributes.final_date,
        last_update=attributes.last_update,
        land_cover_pct=attributes.land_cover or None,
        natura2000_pct=attributes.natura2000_pct,
    )


async def run_effis_sync(
    *,
    bbox: tuple[float, float, float, float],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    client: EffisHttpClient | None = None,
    object_store: ObjectStore | None = None,
    fetch_dnbr: bool = False,
) -> dict[str, int]:
    """Fetch burnt-area perimeters and upsert.

    ``fetch_dnbr=True`` triggers dNBR fetch attempts. Currently the EFFIS
    dNBR endpoint requires a manual data request, so successful raster
    storage is opportunistic — the workflow does not depend on it.
    """
    cli = client or EffisHttpClient()
    store = object_store or build_object_store()

    end = datetime.now(UTC).date()
    start = end - timedelta(days=lookback_days)

    features = list(await cli.fetch_perimeters(bbox=bbox, start=start, end=end))
    log.info("effis.sync.features", count=len(features))

    perimeters = 0
    dnbr_stored = 0

    for feat in features:
        perim = _parse_feature(feat)
        if perim is None:
            continue

        if fetch_dnbr:
            dnbr_bytes = await cli.fetch_dnbr(perimeter_id=perim.id)
            if dnbr_bytes:
                key = f"effis/dnbr/{perim.id}.tif"
                location = await store.put(key, dnbr_bytes, content_type="image/tiff")
                ref_id = await upsert_raster_ref(
                    kind="effis_dnbr",
                    path=key,
                    bbox=perim.geom.envelope,
                    crs="EPSG:4326",
                    checksum_sha256=sha256_hex(dnbr_bytes),
                    size_bytes=len(dnbr_bytes),
                    metadata={
                        "perimeter_id": perim.id,
                        "object_store_location": location,
                    },
                )
                perim = replace(perim, dnbr_path=key, raster_ref_id=ref_id)
                dnbr_stored += 1
                log.info("effis.dnbr.stored", perimeter_id=perim.id, key=key, ref_id=ref_id)

        await upsert_perimeter(perim)
        perimeters += 1

    total_after = await count_perimeters()
    # La severità dipende da *entrambi* i dataset: un perimetro nuovo cambia
    # la densità tanto quanto un hotspot nuovo, quindi il ricalcolo sta su
    # entrambi i percorsi di sync (#67).
    from limen.data.repos.fire_events_repo import refresh_perimeter_frp

    await refresh_perimeter_frp()

    log.info(
        "effis.sync.done",
        perimeters=perimeters,
        dnbr_stored=dnbr_stored,
        total=total_after,
    )
    return {"perimeters": perimeters, "dnbr_stored": dnbr_stored}
