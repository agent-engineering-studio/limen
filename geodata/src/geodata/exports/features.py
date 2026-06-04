"""Export per-cell static features into the operational DB.

The geodata Postgres holds the heavy 930k-polygon PAI mosaic + the
IFFI inventory. The operational DB (often Neon) only needs the
per-cell aggregates that the V1 / V2 engines consume. This exporter
computes the aggregates on the geodata side and ships them across
with one ``UPSERT`` per cell.

What's computed per ``grid_cells`` row in the operational DB:

* ``pai_class_norm``        — most-severe PAI class touching the cell,
  mapped to a numeric scale (``AA=0.10, P1=0.25, P2=0.50, P3=0.75, P4=1.00``).
* ``iffi_density_500``      — count of IFFI features within 500 m of
  the cell centroid, saturated at 3 features → 1.0.
* ``distance_to_iffi_m``    — geodesic distance (m) from the centroid
  to the nearest IFFI feature.

The operational DB never sees a raw geometry — only the three
numeric aggregates per cell, so Neon stays light.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg
import structlog

from geodata.db import connect as connect_geodata

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.exports.features")


PAI_CLASS_NORMS: dict[str, float] = {
    "AA": 0.10,
    "P1": 0.25,
    "P2": 0.50,
    "P3": 0.75,
    "P4": 1.00,
}

IFFI_DENSITY_SATURATION = 3.0
"""Features-per-buffer that maps to a normalised density of 1.0. Mirrors
the V1 engine's saturation so the exporter stays parity-safe with
:mod:`limen.core.scoring.engine`."""


@dataclass(frozen=True, slots=True)
class CellFeatureRow:
    cell_id: str
    pai_class_norm: float | None
    iffi_density_500: float | None
    distance_to_iffi_m: float | None
    flood_hazard_class: str | None = None
    flood_hazard_norm: float | None = None


async def _operational_cells(op: asyncpg.Connection) -> list[tuple[str, str]]:
    """Return ``(cell_id, WKT)`` for every grid cell in the operational DB."""
    rows = await op.fetch("SELECT id, ST_AsText(geom) AS wkt FROM grid_cells")
    return [(str(r["id"]), str(r["wkt"])) for r in rows]


_GEO_FEATURE_SQL = """
WITH cell AS (
    SELECT ST_SetSRID(ST_GeomFromText($1), 4326) AS geom
),
cell_centroid AS (
    SELECT ST_Centroid(geom) AS pt FROM cell
),
pai_intersect AS (
    SELECT p.hazard_class
    FROM pai_landslide_hazard p, cell
    WHERE ST_Intersects(p.geom, cell.geom)
),
flood_intersect AS (
    -- Mirror of pai_intersect on the idraulica mosaic. The ladder is
    -- the same AA/P1..P4 ISPRA convention, so the same class normaliser
    -- (max_pai_norm) can be reused upstream.
    SELECT i.hazard_class
    FROM idraulica_hazard i, cell
    WHERE ST_Intersects(i.geom, cell.geom)
),
buffer AS (
    -- 500 m buffer around the centroid using the geography type so the
    -- distance respects the WGS84 ellipsoid.
    SELECT ST_Buffer(c.pt::geography, 500.0)::geometry AS geom
    FROM cell_centroid c
),
iffi_count AS (
    SELECT COUNT(*)::int AS n
    FROM iffi_landslides i, buffer
    WHERE ST_Intersects(i.geom, buffer.geom)
),
iffi_distance AS (
    SELECT MIN(ST_Distance(i.geom::geography, c.pt::geography)) AS m
    FROM iffi_landslides i, cell_centroid c
)
SELECT
    (SELECT array_agg(hazard_class) FROM pai_intersect)   AS pai_classes,
    (SELECT array_agg(hazard_class) FROM flood_intersect) AS flood_classes,
    (SELECT n FROM iffi_count)                            AS iffi_n,
    (SELECT m FROM iffi_distance)                         AS iffi_distance_m
"""


def max_pai_norm(classes: list[str]) -> float | None:
    """Map the most-severe PAI class in ``classes`` to its normalised value."""
    best: float | None = None
    for cls in classes:
        norm = PAI_CLASS_NORMS.get(str(cls).strip().upper())
        if norm is None:
            continue
        if best is None or norm > best:
            best = norm
    return best


def most_severe_class(classes: list[str]) -> str | None:
    """Pick the most-severe AA/P1..P4 label, ignoring unknown values."""
    best: str | None = None
    best_norm: float | None = None
    for cls in classes:
        key = str(cls).strip().upper()
        norm = PAI_CLASS_NORMS.get(key)
        if norm is None:
            continue
        if best_norm is None or norm > best_norm:
            best_norm = norm
            best = key
    return best


def iffi_density(*, count: int) -> float | None:
    if count <= 0:
        return None
    return min(count / IFFI_DENSITY_SATURATION, 1.0)


async def _compute_features(
    geo: asyncpg.Connection, *, cell_id: str, cell_wkt: str
) -> CellFeatureRow:
    row = await geo.fetchrow(_GEO_FEATURE_SQL, cell_wkt)
    pai_classes = (row["pai_classes"] if row else None) or []
    flood_classes = (row["flood_classes"] if row else None) or []
    iffi_n = int(row["iffi_n"] or 0) if row else 0
    return CellFeatureRow(
        cell_id=cell_id,
        pai_class_norm=max_pai_norm(list(pai_classes)),
        iffi_density_500=iffi_density(count=iffi_n),
        distance_to_iffi_m=(
            float(row["iffi_distance_m"]) if row and row["iffi_distance_m"] is not None else None
        ),
        flood_hazard_class=most_severe_class(list(flood_classes)),
        flood_hazard_norm=max_pai_norm(list(flood_classes)),
    )


_UPSERT_OPERATIONAL_SQL = """
INSERT INTO cell_static_factors (
    cell_id, pai_class_norm, iffi_density_500, distance_to_iffi_m,
    flood_hazard_class, flood_hazard_norm,
    extras, updated_at
)
VALUES ($1, $2, $3, $4, $5, $6, '{}'::jsonb, now())
ON CONFLICT (cell_id) DO UPDATE
SET pai_class_norm     = COALESCE(EXCLUDED.pai_class_norm,
                                  cell_static_factors.pai_class_norm),
    iffi_density_500   = COALESCE(EXCLUDED.iffi_density_500,
                                  cell_static_factors.iffi_density_500),
    distance_to_iffi_m = COALESCE(EXCLUDED.distance_to_iffi_m,
                                  cell_static_factors.distance_to_iffi_m),
    flood_hazard_class = COALESCE(EXCLUDED.flood_hazard_class,
                                  cell_static_factors.flood_hazard_class),
    flood_hazard_norm  = COALESCE(EXCLUDED.flood_hazard_norm,
                                  cell_static_factors.flood_hazard_norm),
    updated_at         = now()
"""


async def export_cell_features(*, operational_dsn: str) -> int:
    """Walk every operational cell and upsert the geodata-derived features.

    Returns the CLI exit code: 0 on success. Per-cell failures are
    logged + counted, not raised — the operational DB stays consistent
    cell-by-cell.
    """
    written = 0
    errors = 0
    async with connect_geodata() as geo:
        op = await asyncpg.connect(operational_dsn)
        try:
            cells = await _operational_cells(op)
            _log.info("geodata.export_features.start", cells=len(cells))
            for cell_id, cell_wkt in cells:
                try:
                    features = await _compute_features(geo, cell_id=cell_id, cell_wkt=cell_wkt)
                    await op.execute(
                        _UPSERT_OPERATIONAL_SQL,
                        cell_id,
                        features.pai_class_norm,
                        features.iffi_density_500,
                        features.distance_to_iffi_m,
                        features.flood_hazard_class,
                        features.flood_hazard_norm,
                    )
                    written += 1
                except Exception as exc:
                    errors += 1
                    _log.warning(
                        "geodata.export_features.cell_failed",
                        cell_id=cell_id,
                        error=str(exc),
                        error_type=type(exc).__name__,
                    )
        finally:
            await op.close()
    _log.info(
        "geodata.export_features.done",
        cells_written=written,
        errors=errors,
    )
    return 0


__all__ = [
    "IFFI_DENSITY_SATURATION",
    "PAI_CLASS_NORMS",
    "CellFeatureRow",
    "export_cell_features",
    "iffi_density",
    "max_pai_norm",
    "most_severe_class",
]
