# limen-geodata

Geo-Data Service for Limen — downloads the official ISPRA IdroGEO
landslide-hazard datasets into a dedicated PostGIS volume on the
Aruba VPS, exports per-cell static features into the operational
DB, produces PMTiles for the public map, and exposes an
`ispra-geo` MCP server for agents.

Implements project doc §3.3.4-ter. **Never** runs on Neon or in the
hourly critical path.

## Quickstart

```bash
# Bring up the geodata profile on the VPS (Postgres + init job + MCP)
docker compose -f infra/docker/docker-compose.geodata.yml --profile geodata up -d

# From the host: inspect the manifest
uv run limen geodata list

# Trigger the init pipeline manually (the compose runs it automatically)
uv run limen geodata init --dry-run
```

## Layout

```
geodata/
├── datasets.yaml             # manifest (single source of truth)
├── pyproject.toml            # workspace member (limen-geodata)
└── src/geodata/
    ├── manifest.py           # Pydantic v2 schema
    ├── parsers.py            # Prompt-2 logic, self-contained
    ├── cli.py                # internal CLI runners
    ├── init/                 # downloader + unzipper + importer
    ├── exports/              # features.py + pmtiles.py
    └── mcp/                  # FastMCP server `ispra-geo`
```

Designed to be extracted into a standalone repo with a single
directory move — nothing in `src/geodata/*` imports from `limen.*`.
