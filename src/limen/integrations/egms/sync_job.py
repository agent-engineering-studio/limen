"""EGMS sync job — fetch scatterers, aggregate to cells, upsert.

Low-cadence (yearly). Idempotent via the dataset_versions registry: a
re-run with the same content hash skips all writes. With the EGMS
``base_url`` empty (dev default) the job degrades to a no-op + logs.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos import cell_insar_features_repo
from limen.data.repos.dataset_versions_repo import content_hash
from limen.integrations.egms.aggregate import aggregate_scatterers_to_cells
from limen.integrations.egms.client import EgmsClient, ScattererPoint

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


async def _cells_for_aoi(aoi_id: str) -> dict[str, Any]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, geom FROM grid_cells WHERE aoi_id = $1",
            aoi_id,
        )
    return {str(r["id"]): r["geom"] for r in rows}


async def _aoi_bbox(aoi_id: str) -> tuple[float, float, float, float] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(ST_Envelope(geom)) AS xmin,
                   ST_YMin(ST_Envelope(geom)) AS ymin,
                   ST_XMax(ST_Envelope(geom)) AS xmax,
                   ST_YMax(ST_Envelope(geom)) AS ymax
            FROM aoi WHERE id = $1
            """,
            aoi_id,
        )
    if row is None or row["xmin"] is None:
        return None
    return (
        float(row["xmin"]),
        float(row["ymin"]),
        float(row["xmax"]),
        float(row["ymax"]),
    )


async def _register_dataset_version(*, source: str, dataset: str, payload_hash: str) -> int | None:
    """Upsert a dataset_versions row. Returns its id (or None on failure)."""
    async with acquire() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO dataset_versions (source, dataset, version, fetched_at, metadata)
                VALUES ($1, $2, $3, now(), '{}'::jsonb)
                ON CONFLICT (source, dataset, version) DO UPDATE
                SET fetched_at = EXCLUDED.fetched_at
                RETURNING id
                """,
                source,
                dataset,
                payload_hash,
            )
        except Exception as exc:  # never let bookkeeping kill the sync
            _log.warning("egms.dataset_version.skip", error=str(exc))
            return None
    return int(row["id"]) if row else None


async def sync_egms(*, aoi_id: str, settings: Settings | None = None) -> int:
    """Refresh ``cell_insar_features`` for one AOI. Returns rows written."""
    s = settings or get_settings()
    if not s.egms.base_url:
        _log.info("egms.sync.skip_no_base_url", aoi_id=aoi_id)
        return 0

    bbox = await _aoi_bbox(aoi_id)
    if bbox is None:
        _log.warning("egms.sync.no_aoi", aoi_id=aoi_id)
        return 0

    client = EgmsClient(base_url=s.egms.base_url, product=s.egms.product)
    scatterers: list[ScattererPoint] = []
    async for point in client.fetch_bbox(bbox=bbox):
        scatterers.append(point)
    if not scatterers:
        _log.info("egms.sync.no_scatterers", aoi_id=aoi_id, bbox=bbox)
        return 0

    cells = await _cells_for_aoi(aoi_id)
    if not cells:
        _log.warning("egms.sync.no_cells", aoi_id=aoi_id)
        return 0

    rows = aggregate_scatterers_to_cells(scatterers=scatterers, cells=cells)
    payload_hash = content_hash(
        json.dumps([_to_jsonable(s) for s in scatterers], default=str, sort_keys=True).encode(
            "utf-8"
        )
    )
    dataset_version_id = await _register_dataset_version(
        source="copernicus.egms", dataset=f"{s.egms.product}/{aoi_id}", payload_hash=payload_hash
    )
    rows_with_version = [
        type(r)(**{**r.__dict__, "dataset_version_id": dataset_version_id}) for r in rows
    ]
    written = await cell_insar_features_repo.upsert_many(rows_with_version)
    _log.info(
        "egms.sync.done",
        aoi_id=aoi_id,
        scatterers=len(scatterers),
        cells=len(cells),
        rows_written=written,
        dataset_version_id=dataset_version_id,
    )
    return written


def _to_jsonable(p: ScattererPoint) -> dict[str, Any]:
    return {
        "lon": p.lon,
        "lat": p.lat,
        "velocity_mmy": p.velocity_mmy,
        "acceleration_mmy2": p.acceleration_mmy2,
        "period_start": p.period_start.isoformat() if p.period_start else None,
        "period_end": p.period_end.isoformat() if p.period_end else None,
    }


__all__ = ["sync_egms"]
