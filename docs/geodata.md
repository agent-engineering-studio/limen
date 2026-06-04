# Geo-Data Service (§3.3.4-ter)

The Geo-Data Service is a **separate VPS-only stack** that downloads
the heavy national ISPRA datasets (~930k-polygon PAI mosaic, the
per-region IFFI inventory, the IFFI Dizionari JSONs), imports them
into its own PostGIS, and serves them three ways:

| Surface | How |
|---|---|
| Per-cell features | `limen geodata export-features --to <operational-dsn>` writes three numeric columns per cell into the operational `cell_static_factors`. Neon stays light. |
| Static map tiles  | `limen geodata make-pmtiles` produces `.pmtiles` per static layer in `$GEODATA_PMTILES_DIR`. The map serves them without DB load. |
| MCP for agents    | `ispra-geo` (FastMCP) exposes `hazard_at` / `iffi_query` / `pai_summary` / `dataset_status` / `refresh`. Read-only; refresh admin-token guarded. |

The service is **opt-in** via the `geodata` compose profile and is
not part of the hourly critical path. With the profile inactive,
Limen runs identically to before Phase 12.

## Layout

```
limen/
├── geodata/                       # workspace member, extractable as a standalone repo
│   ├── pyproject.toml
│   ├── README.md
│   ├── Dockerfile                 # small image — NO data baked in
│   ├── claude_desktop_config.example.json
│   └── src/geodata/
│       ├── datasets.yaml          # manifest (single source of truth)
│       ├── manifest.py            # Pydantic v2 schema
│       ├── parsers.py             # Prompt-2 logic, duplicated
│       ├── db.py                  # asyncpg + schema DDL
│       ├── cli.py                 # internal runners
│       ├── init/                  # downloader + safe_unzip + importers + runner
│       ├── exports/               # features.py + pmtiles.py
│       └── mcp/                   # tools.py + server.py
└── infra/docker/
    └── docker-compose.geodata.yml # `geodata` profile — only on the VPS
```

## CLI

```bash
limen geodata list                              # print the manifest as JSON
limen geodata init [--only NAME[,NAME]] [--region REG] [--force] [--dry-run]
limen geodata export-features --to <operational-dsn>
limen geodata make-pmtiles
limen geodata mcp --transport {stdio,http}
```

## Manifest

`src/geodata/datasets.yaml`. Single source of truth — adding a
dataset means adding an entry, no code change. The Pydantic schema
in `manifest.py` enforces:

* every URL starts with `https://idrogeo.isprambiente.it/` (the
  loader refuses anything else by construction);
* `name` matches `^[a-z][a-z0-9_]*$` so it's a safe natural key;
* `format` is one of `shapefile-zip | geojson-zip | json`;
* no duplicate names within a manifest.

The shipped manifest pre-populates the V1 pilot:

| Name | Kind | Notes |
|---|---|---|
| `pai_frane` | shapefile-zip → `pai_landslide_hazard` | National PAI mosaic |
| `idraulica` | shapefile-zip → `idraulica_hazard` | **enabled: false** in V1 (future flood module) |
| `iffi_puglia_*` × 4 | shapefile-zip → `iffi_landslides` | line/poly/aree/dgpv layers, region=puglia |
| `iffi_basilicata_*` × 4 | shapefile-zip → `iffi_landslides` | line/poly/aree/dgpv layers, region=basilicata |
| `iffi_dizionari_*` × 3 | json → `iffi_lookup_*` | cause / movimento / litologia |

## Init pipeline

`limen geodata init` is idempotent and resumable:

1. **Streaming download** (httpx + tenacity retry — 4 attempts,
   exponential backoff capped at 60 s, 5xx/429/transport errors are
   retryable). No full file in memory.
2. **Skip-if-unchanged**: SHA-256 against the most-recent
   `dataset_versions` row for the same `name`. `--force` re-imports.
3. **Safe unzip**: refuses path-traversal entries + absolute paths +
   symlinks. JSONs go straight to the importer (no archive).
4. **Format-specific import** via `pyogrio` → PostGIS. Geometries
   are validated (`make_valid`) and reprojected to EPSG:4326. PAI
   classes are normalised to the canonical `AA/P1..P4` ladder
   (unknowns survive as `UNKNOWN`, never dropped). IFFI features
   carry their `geom_type` (`piff_line | piff_poly | aree_poly |
   dgpv_poly`) so the same logical feature in two layers doesn't
   collide on the primary key.
5. **Record version** + clean temp files (always, even on error).

One failing dataset never aborts the others. Per-dataset outcome is
logged and counted; the runner returns a non-zero exit code only if
*any* dataset failed.

## Exports

* `limen geodata export-features --to <operational-dsn>` reads every
  `grid_cells` row from the operational DB, computes
  `pai_class_norm` (most-severe class mapped to a scalar),
  `iffi_density_500` (IFFI count within 500 m geodesic buffer, saturated
  at 3 → 1.0), and `distance_to_iffi_m` (geodesic distance from the
  centroid). Single `UPSERT` per cell — only the three numeric
  columns cross the wire, so Neon stays light.

* `limen geodata make-pmtiles` streams a FeatureCollection per layer
  to `$GEODATA_GEOJSON_DIR` (asyncpg cursor with `prefetch=500` keeps
  memory bounded for the 930k-polygon mosaic), then invokes the
  system `tippecanoe` binary to produce `.pmtiles` into
  `$GEODATA_PMTILES_DIR`. The map consumes them statically — zero DB
  load at view time.

## `ispra-geo` MCP server

| Tool | Inputs | Notes |
|---|---|---|
| `hazard_at` | `lat`, `lon` | Most-severe PAI class touching the point + authority + region. |
| `iffi_query` | `bbox` OR `region`, optional `movement_type`, `limit` (≤500) | Decodes `movement_type` via the Dizionario. |
| `pai_summary` | `region` OR `bbox` | Per-class feature count + km² area (geodesic). |
| `dataset_status` | — | Latest checksum + row count per manifest entry. |
| `refresh` | `dataset`, `admin_token` | Re-runs the init pipeline. Requires `MCP_ADMIN_TOKEN`; no env ⇒ disabled. |

Transports: `stdio` for Claude Desktop, `http` (port 8765) for the
container. See `geodata/claude_desktop_config.example.json` for a
ready-to-use Claude Desktop entry.

## Deployment

```bash
# On the Aruba VPS only:
docker compose -f infra/docker/docker-compose.geodata.yml \
  --profile geodata up -d
```

Three services come up under that profile:

1. `geodata-db` — Postgres+PostGIS on port `55432` (different from
   the operational Postgres on 5432).
2. `geodata-init` — one-shot job running `limen geodata init`.
3. `ispra-geo-mcp` — FastMCP on `http://<host>:8765`.

The image carries the Python code, GDAL/PROJ libs, and tippecanoe —
**no dataset bytes**. Data lives in the named Postgres volume only.

### Out of scope

GeoServer / WMS self-hosting, authentication beyond the MCP admin
token, running the profile on Neon or in the hourly critical path,
flood-module logic (the `idraulica` dataset imports but stays unused
in V1).
