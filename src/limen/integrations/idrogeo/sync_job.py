"""ISPRA IdroGEO sync job: idempotent download → parse → upsert.

Flow:

1. Fetch IFFI / PAI / susceptibility WFS payloads clipped to the AOI.
2. Compute a stable content hash over the concatenated bytes.
3. If ``dataset_versions(source='ispra', dataset='idrogeo', version=hash)``
   already exists, the data is unchanged — **skip all writes** and return
   ``{"skipped": True}``.
4. Otherwise, parse features, upsert in transactional batches keyed by
   IFFI / PAI id, and finally record the new dataset version.

Susceptibility is *fetched* and the version is *recorded*, but the
per-cell rasterisation/zonal-stats step is the responsibility of
:mod:`limen.integrations.static_bootstrap` — keeping ingest and feature
computation separate avoids accidentally re-running heavy raster ops
every weekly sync.
"""

from __future__ import annotations

import json
from typing import Any

from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.repos.aoi_repo import get_aoi
from limen.data.repos.dataset_versions_repo import (
    content_hash,
)
from limen.data.repos.dataset_versions_repo import (
    find as find_version,
)
from limen.data.repos.dataset_versions_repo import (
    record as record_version,
)
from limen.data.repos.iffi_repo import IFFILandslide, count_landslides
from limen.data.repos.iffi_repo import upsert_many as upsert_iffi
from limen.data.repos.pai_repo import PAIHazard, count_pai
from limen.data.repos.pai_repo import upsert_many as upsert_pai
from limen.integrations.idrogeo.client import IdroGeoHttpClient
from limen.integrations.idrogeo.parsers import parse_iffi_feature, parse_pai_feature

log = get_logger(__name__)


def _features_to_hash(*feature_lists: list[dict[str, Any]]) -> str:
    """Compute a stable content hash across all fetched features.

    Sorted JSON serialisation keeps the hash stable regardless of WFS
    response ordering.
    """
    chunks: list[bytes] = []
    for feats in feature_lists:
        canonical = json.dumps(feats, sort_keys=True, default=str).encode("utf-8")
        chunks.append(canonical)
    return content_hash(chunks)


async def run_idrogeo_sync(
    *,
    aoi_id: str,
    client: IdroGeoHttpClient | None = None,
    cql_filter_iffi: str | None = None,
) -> dict[str, Any]:
    """Run the IdroGEO sync for ``aoi_id``.

    Returns either ``{"skipped": True, "version": <hash>, "version_id": <id>}``
    (unchanged data) or a dict with insert counters.
    """
    cli = client or IdroGeoHttpClient()
    aoi = await get_aoi(aoi_id)
    if aoi is None:
        raise ValueError(f"AOI not found: {aoi_id!r}")

    aoi_geom: BaseGeometry = aoi.geom

    iffi_feats = list(await cli.fetch_iffi(aoi_geom=aoi_geom, cql_filter=cql_filter_iffi))
    pai_feats = list(await cli.fetch_pai(aoi_geom=aoi_geom))
    susc_feats = list(await cli.fetch_susceptibility(aoi_geom=aoi_geom))

    version = _features_to_hash(iffi_feats, pai_feats, susc_feats)
    existing = await find_version("ispra", "idrogeo", version)
    if existing is not None:
        log.info(
            "idrogeo.sync.skip",
            aoi_id=aoi_id,
            reason="content unchanged",
            version=version,
            version_id=existing.id,
        )
        return {
            "skipped": True,
            "version": version,
            "version_id": existing.id,
            "iffi": 0,
            "pai": 0,
            "susceptibility_features": len(susc_feats),
        }

    # Record the new version FIRST so per-row writes can reference it.
    version_id = await record_version(
        source="ispra",
        dataset="idrogeo",
        version=version,
        metadata={
            "aoi_id": aoi_id,
            "iffi_count": len(iffi_feats),
            "pai_count": len(pai_feats),
            "susceptibility_count": len(susc_feats),
        },
    )

    iffi_items: list[IFFILandslide] = []
    for feat in iffi_feats:
        iffi = parse_iffi_feature(feat)
        if iffi is None:
            continue
        iffi_items.append(
            IFFILandslide(
                id=iffi.id,
                movement_type=iffi.movement_type,
                state=iffi.state,
                velocity_class=iffi.velocity_class,
                occurrence_date=iffi.occurrence_date,
                geom=iffi.geom,
                dataset_version_id=version_id,
                attributes=iffi.attributes,
            )
        )
    iffi_written = await upsert_iffi(iffi_items)

    pai_items: list[PAIHazard] = []
    for feat in pai_feats:
        pai = parse_pai_feature(feat)
        if pai is None:
            continue
        pai_items.append(
            PAIHazard(
                id=pai.id,
                hazard_class=pai.hazard_class,
                authority=pai.authority,
                geom=pai.geom,
                dataset_version_id=version_id,
                attributes=pai.attributes,
            )
        )
    pai_written = await upsert_pai(pai_items)

    log.info(
        "idrogeo.sync.done",
        aoi_id=aoi_id,
        version=version,
        version_id=version_id,
        iffi_features=len(iffi_feats),
        iffi_written=iffi_written,
        pai_features=len(pai_feats),
        pai_written=pai_written,
        susceptibility_features=len(susc_feats),
        iffi_total=await count_landslides(),
        pai_total=await count_pai(),
    )
    return {
        "skipped": False,
        "version": version,
        "version_id": version_id,
        "iffi": iffi_written,
        "pai": pai_written,
        "susceptibility_features": len(susc_feats),
    }
