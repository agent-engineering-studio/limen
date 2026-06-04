#!/usr/bin/env bash
# Limen demo walkthrough — print the canonical first-time interaction
# against the docker-compose.demo.yml stack. Designed to be readable
# and copy-paste-friendly; nothing in here mutates state.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8080}"
TILES_URL="${TILES_URL:-http://localhost:7800}"
MAP_URL="${MAP_URL:-http://localhost:5173}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"

heading() {
  printf '\n\033[1;34m== %s ==\033[0m\n' "$1"
}

heading "Limen demo — quick tour"

cat <<EOF
Stack:
  • API           ${API_URL}/docs
  • pg_tileserv   ${TILES_URL}
  • Map           ${MAP_URL}                (start with: docker compose --profile frontend up frontend)
  • Grafana LGTM  ${GRAFANA_URL}            (start with: make observability)

The compose 'make demo' target has already:
  1. brought up Postgres + PostGIS + API + pg_tileserv + Mosquitto;
  2. seeded the Puglia + Basilicata AOIs and a 1 km grid;
  3. populated cell_static_factors with the IFFI density + PAI bootstrap;
  4. fired one monitoring workflow for Puglia (top 25 cells).

EOF

heading "Try these calls"

cat <<EOF
# Health + readiness
curl -s ${API_URL}/health | jq
curl -s ${API_URL}/ready  | jq

# Browse AOIs
curl -s ${API_URL}/api/aoi | jq

# Run another monitoring cycle on demand
curl -s -X POST ${API_URL}/api/monitor/it-puglia \\
  -H 'content-type: application/json' \\
  -d '{"cell_limit": 25}' | jq '.assessment | {n_cells, cells_by_level, briefing_it}'

# Latest persisted assessment
curl -s ${API_URL}/api/aoi/it-puglia/risk/latest | jq '{cells_high_or_above, cells_by_level, briefing_it}'

# Per-cell breakdown — replace with one of the cell ids printed above
curl -s "${API_URL}/api/cell/it-puglia%7C0%7C0/breakdown" | jq

# Recent alerts (default threshold = High, trailing 72 h)
curl -s "${API_URL}/api/alerts?threshold=High&since_hours=72&limit=20" | jq

# Tile preview — opens in the browser if you have a viewer for .pbf
echo "Tile URL: ${API_URL}/api/tiles/public.mv_latest_risk/8/256/256.pbf"

EOF

heading "Next steps"

cat <<EOF
  • Bring up the frontend:
      docker compose -f infra/docker/docker-compose.demo.yml --profile frontend up -d
      open ${MAP_URL}

  • Run the Oct-2018 backtest:
      make backtest
      ls reports/

  • Bring up observability and open Grafana:
      make observability
      open ${GRAFANA_URL}
EOF
