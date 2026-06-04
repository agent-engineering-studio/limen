# Data model

PostgreSQL 16 + PostGIS 3.5. All geometries are stored in **EPSG:4326**;
metric ops (buffers, distances) reproject to **EPSG:3035** (LAEA Europe)
in application code or in PostGIS `ST_Transform` calls.

Migrations are plain SQL under
[`src/limen/data/migrations/`](../src/limen/data/migrations/) and run
through the idempotent
[`limen.data.migrate`](../src/limen/data/migrate.py) runner. Each
applied file is hashed and recorded in `schema_migrations` — editing an
applied file is a hard error.

## Tables (in dependency order)

### `dataset_versions`

A registry of every external dataset Limen has ingested. The sync jobs
compute a content hash over the raw payload and look up
`(source, dataset, version)` here before writing — if the version
exists, **all writes are skipped** (idempotency contract).

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `source` | text | e.g. `"ispra"`, `"openmeteo"` |
| `dataset` | text | e.g. `"idrogeo"` |
| `version` | text | content hash or source revision label |
| `fetched_at` | timestamptz | |
| `metadata` | jsonb | aoi_id, payload size, etc. |

### `aoi`

Area of Interest — a region/province/municipality polygon.

| Column | Type | Notes |
|---|---|---|
| `id` | text PK | e.g. `"it-puglia"` |
| `name` | text | |
| `kind` | text | default `"region"` |
| `geom` | `geometry(MultiPolygon, 4326)` | GiST index |
| `bbox` | `geometry(Polygon, 4326)` | generated stored — `ST_Envelope(geom)` |

### `grid_cells`

1 km² discretisation per AOI. ID is deterministic
(`<aoi_id>|<row>|<col>`) so a re-seed is a no-op.

| Column | Type | Notes |
|---|---|---|
| `id` | text PK | |
| `aoi_id` | text → aoi(id) | |
| `row_idx`, `col_idx` | integer | |
| `geom` | `geometry(Polygon, 4326)` | GiST |
| `centroid` | `geometry(Point, 4326)` | generated stored |
| `area_km2` | double precision | |

### `iffi_landslides` + `pai_hazard` + `susceptibility`

Phase-1 inventories populated by the ISPRA IdroGEO sync (Phase 2).
`pai_hazard.hazard_class_norm ∈ [0, 1]` is the normalised PAI class
(AA → 0.20, P1 → 0.40, …, P4 → 1.00) consumed by the scoring engine.

### `cell_static_factors`

One row per grid cell. Holds the static features the V1 engine reads
plus the (still-NULL) exposure variables the AlertDispatchExecutor uses
for prioritisation.

| Column | Source | Phase |
|---|---|---|
| `slope_deg`, `aspect_deg`, `elevation_m`, `twi`, `curvature` | TINITALY DEM (not yet ingested) | future |
| `lithology`, `litho_weight`, `dist_faults_m` | ISPRA Carta Geologica (future) | future |
| `landuse_code` | CORINE (future) | future |
| `iffi_density_500`, `distance_to_iffi_m` | `limen bootstrap-static` (PostGIS-only) | Phase 2 |
| `pai_class_norm` | `limen bootstrap-static` (PostGIS-only) | Phase 2 |
| `s_static` | `limen calibrate` | Phase 3 |
| `population_count`, `buildings_count`, `infra_density_norm` | exposure ingest (future) | Phase 7 stub |

### `seismic_events` (Phase 2)

| Column | Type |
|---|---|
| `id` (text PK) | INGV eventID |
| `origin_time` (timestamptz) | |
| `magnitude` (double) | |
| `geom` (Point, 4326) | |
| `shakemap_path` (text, NULL OK) | ObjectStore key when a ShakeMap exists |
| `raster_ref_id` (bigint → raster_refs) | |

### `fire_perimeters` (Phase 2)

EFFIS burnt-area polygons (date, area_ha, geom, optional dNBR raster
ref). The post-fire scoring component derives `months_since_fire`
from the most-recent perimeter intersecting the AOI.

### `risk_assessments` (Phase 4 writes here)

One row per scored cell per workflow run.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial PK | |
| `cell_id` | text → grid_cells(id) | |
| `computed_at` | timestamptz | |
| `horizon` | text | e.g. `"24h"` |
| `score` | double | 0..1 |
| `class` | text | None/Low/Moderate/High/VeryHigh |
| `factors` | jsonb | s/m/e/f/h breakdown + sub-terms |
| `explanation` | jsonb | analysis (RiskAnalyst) + briefing_it (Briefing) |
| `pipeline_version` | text | |
| `dataset_versions` | bigint[] | links back to `dataset_versions` (V1.5+) |

### `mv_latest_risk` (matview, Phase 6)

`grid_cells ⨝ latest risk_assessments per cell`. UNIQUE index on
`cell_id` so `REFRESH MATERIALIZED VIEW CONCURRENTLY` doesn't block
readers. Always refreshed via the SQL function
`refresh_mv_latest_risk()` — never `REFRESH` directly.

### `alert_dispatches` (Phase 7)

Append-only audit of every alert the AlertDispatchExecutor decided to
fire. Used by:

* The dedup query (`cells_dispatched_within(cell_ids, window)`) to
  suppress repeats inside `ALERT__DEDUP_WINDOW_MINUTES`.
* Operators inspecting recent activity (`GET /api/alerts`).

| Column | Type |
|---|---|
| `id` (bigserial PK) | |
| `cell_id` (text → grid_cells) | |
| `aoi_id` (text → aoi) | |
| `level`, `score`, `priority` | |
| `channels` (jsonb) | `{channel_name: bool}` outcomes |
| `summary` (text) | the Italian summary that was sent |
| `dispatched_at` (timestamptz) | |

### Supporting tables

* `raster_refs` — only metadata (path + bbox + checksum). Bytes live
  in the `ObjectStore` (filesystem / S3-compatible).
* `app_cache` — UNLOGGED key/value JSONB with TTL.
* `norm_stats` — per-AOI min/max statistics persisted by
  `limen calibrate` so the scoring is reproducible.

## Conventions

* Every geometry column is **EPSG:4326** and has a GiST index.
* Metric operations (`ST_DWithin`, `ST_Distance`) reproject to
  **EPSG:3035** in the SQL or in the application layer.
* All check constraints are explicit (`score BETWEEN 0 AND 1`,
  `hazard_class_norm BETWEEN 0 AND 1`, …).
* JSONB columns store dotted-key payloads — neither array indices nor
  PostgreSQL operators expose them as first-class columns; the
  application normalises at read time.

## ERD-by-FK summary

```
aoi(id) ◀── grid_cells(aoi_id)
grid_cells(id) ◀── cell_static_factors(cell_id)
                ◀── risk_assessments(cell_id)
                ◀── susceptibility(cell_id)
                ◀── alert_dispatches(cell_id)
dataset_versions(id) ◀── iffi_landslides(dataset_version_id)
                      ◀── pai_hazard(dataset_version_id)
                      ◀── seismic_events(dataset_version_id)
                      ◀── fire_perimeters(dataset_version_id)
                      ◀── raster_refs(dataset_version_id)
raster_refs(id) ◀── seismic_events(raster_ref_id)
                ◀── fire_perimeters(raster_ref_id)
```
