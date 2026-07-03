# Limen — developer Makefile

UV ?= uv

# Base PostGIS image for the built db image. Upstream postgis/postgis lacks an
# arm64 manifest, so on Apple Silicon default to the multi-arch imresamu image.
ifeq ($(shell uname -m),arm64)
POSTGIS_BASE ?= imresamu/postgis:16-3.5
else
POSTGIS_BASE ?= postgis/postgis:16-3.5
endif
export POSTGIS_BASE
COMPOSE_DEV  := infra/docker/docker-compose.dev.yml
COMPOSE_DEMO := infra/docker/docker-compose.demo.yml
COMPOSE_OBS  := infra/docker/docker-compose.observability.yml
COMPOSE_GEOSERVER := infra/docker/docker-compose.geoserver.yml
# Unified stack: operational services + GeoServer, one project, one network.
COMPOSE_ALL  := -f $(COMPOSE_DEMO) -f $(COMPOSE_GEOSERVER) -p limen
UP_PROFILES  := --profile geoserver --profile frontend

.PHONY: help install \
        up down \
        up-dev down-dev logs migrate seed bootstrap-static calibrate backtest serve \
        demo demo-down demo-walkthrough \
        observability observability-down \
        geoserver-up geoserver-down geoserver-init geoserver-logs geoserver-sync dtm-vrt \
        test test-unit test-integration test-frontend \
        lint format typecheck check clean

help:
	@echo "Limen — common developer targets"
	@echo ""
	@echo "Full stack (one command)"
	@echo "  make up                 start operational + GeoServer stack, seed + geoserver-sync (idempotent)"
	@echo "  make down               tear down the full stack"
	@echo ""
	@echo "Backend setup"
	@echo "  make install            install runtime + dev deps via uv"
	@echo "  make up-dev             start local Postgres+PostGIS (compose dev)"
	@echo "  make down-dev           stop local Postgres+PostGIS"
	@echo "  make logs               tail Postgres container logs"
	@echo "  make migrate            apply pending SQL migrations"
	@echo "  make seed               apply migrations + seed Puglia/Basilicata AOIs + grids"
	@echo "  make bootstrap-static   fill cell_static_factors (IFFI density + PAI + distance)"
	@echo "  make calibrate          run §2.5 calibration (s_static + S↔ISPRA gate)"
	@echo "  make backtest           replay the Oct 2018 storm and write the report"
	@echo "  make serve              FastAPI on :8080"
	@echo ""
	@echo "End-to-end demo"
	@echo "  make demo               bring up the full Postgres+API+pg_tileserv+Mosquitto stack"
	@echo "                          + seed + bootstrap-static + monitor-once for Puglia"
	@echo "  make demo-walkthrough   print the curl examples + browser URLs"
	@echo "  make demo-down          tear down the demo stack"
	@echo "  make observability      bring up Grafana LGTM (alongside demo)"
	@echo "  make observability-down stop the observability stack"
	@echo ""
	@echo "GeoServer vector-data layer (opt-in, mcp-geo-server)"
	@echo "  make geoserver-up       GeoServer + PostGIS + web UI + MCP agent + bootstrap"
	@echo "  make geoserver-init     (re)load shapefiles into PostGIS + publish + style"
	@echo "  make geoserver-logs     tail the GeoServer stack logs"
	@echo "  make geoserver-down     tear down the GeoServer stack (keep volumes)"
	@echo ""
	@echo "Quality"
	@echo "  make test               backend pytest"
	@echo "  make test-unit          unit tests only (no Docker)"
	@echo "  make test-integration   integration tests (Docker required)"
	@echo "  make test-frontend      Vitest + ESLint inside frontend/"
	@echo "  make lint               ruff check"
	@echo "  make format             ruff format"
	@echo "  make typecheck          mypy --strict"
	@echo "  make check              lint + typecheck + tests"
	@echo "  make clean              caches + build artefacts"

# ---------------------------------------------------------------------------
# Full stack (operational + GeoServer) — one command, idempotent data refresh
# ---------------------------------------------------------------------------
up:
	docker compose $(COMPOSE_ALL) $(UP_PROFILES) up -d --build
	@echo "[up] waiting for the API to become ready…"
	@for i in $$(seq 1 40); do \
	  docker compose $(COMPOSE_ALL) exec -T api python -c \
	    "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/ready', timeout=2).status==200 else 1)" \
	    >/dev/null 2>&1 && break; \
	  sleep 3; \
	done
	@echo "[up] idempotent data refresh: seed (AOIs + grid) + geoserver-sync (IFFI + PAI)"
	docker compose $(COMPOSE_ALL) exec -T api limen seed
	docker compose $(COMPOSE_ALL) exec -T api limen geoserver-sync
	@echo ""
	@echo "[up] Stack ready:"
	@echo "   API      http://localhost:8080/docs      Frontend  http://localhost:5173"
	@echo "   GeoServer http://localhost:8081/geoserver Web UI    http://localhost:8000"
	@echo ""
	@echo "[up] One-off: per-cell static factors incl. DTM slope (~40 min on the 5 m DTM),"
	@echo "     run on the HOST so it reads the DTM + .env:  make bootstrap-static"

down:
	docker compose $(COMPOSE_ALL) $(UP_PROFILES) down

# ---------------------------------------------------------------------------
# Docker images — build every Limen-owned image (GeoServer/pg_tileserv/etc.
# are pulled, not built). Tags match the compose files. Built for
# linux/amd64 (the self-hosted VPS deploy target) so it works from an
# Apple-Silicon dev box too — the postgis/postgis base has no arm64 manifest.
# ---------------------------------------------------------------------------
PLATFORM ?= linux/amd64

build-images:
	docker build --platform $(PLATFORM) -f infra/postgres/Dockerfile.db -t limen/postgres:16-3.5 infra/postgres
	docker build --platform $(PLATFORM) -f infra/docker/Dockerfile.api  -t limen/api:0.1 .
	docker build --platform $(PLATFORM) -f geodata/Dockerfile           -t limen/geodata:0.1 .
	( cd frontend && npm ci && npm run build )
	@echo "[build-images] built limen/postgres:16-3.5, limen/api:0.1, limen/geodata:0.1 ($(PLATFORM)) + frontend dist/"

# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
install:
	$(UV) sync --all-groups

up-dev:
	docker compose -f $(COMPOSE_DEV) up -d --build

down-dev:
	docker compose -f $(COMPOSE_DEV) down

logs:
	docker compose -f $(COMPOSE_DEV) logs -f postgres

migrate:
	$(UV) run limen migrate

seed:
	$(UV) run limen seed

bootstrap-static:
	$(UV) run limen bootstrap-static

calibrate:
	$(UV) run limen calibrate

backtest:
	$(UV) run limen backtest

ingest-events:
	$(UV) run limen ingest-events

# Full reproducible data init for a fresh machine (all 20 regions + ITALICA
# truth set auto-downloaded from Zenodo). Idempotent: safe to re-run.
init:
	$(UV) run limen migrate
	$(UV) run limen seed
	$(UV) run limen ingest-events
	$(UV) run limen bootstrap-static
	$(UV) run limen calibrate

serve:
	$(UV) run limen serve

# ---------------------------------------------------------------------------
# Demo / end-to-end
# ---------------------------------------------------------------------------
demo:
	docker compose -f $(COMPOSE_DEMO) up -d --build
	@echo "[demo] waiting for the API to become ready…"
	@for i in $$(seq 1 40); do \
	  status=$$(docker compose -f $(COMPOSE_DEMO) exec -T api python -c \
	    "import urllib.request,sys; \
	     sys.exit(0 if urllib.request.urlopen('http://localhost:8080/ready', timeout=2).status==200 else 1)" \
	    >/dev/null 2>&1 && echo ok || echo no); \
	  [ "$$status" = "ok" ] && break; \
	  sleep 3; \
	done
	@echo "[demo] seeding + bootstrap + first monitoring cycle for Puglia"
	docker compose -f $(COMPOSE_DEMO) exec -T api limen seed
	docker compose -f $(COMPOSE_DEMO) exec -T api limen bootstrap-static
	docker compose -f $(COMPOSE_DEMO) exec -T -e LIMEN_MONITOR_AOI=it-puglia \
	    -e LIMEN_MONITOR_CELL_LIMIT=25 api limen monitor-once
	@$(MAKE) demo-walkthrough

demo-down:
	docker compose -f $(COMPOSE_DEMO) down

demo-walkthrough:
	@bash scripts/demo_walkthrough.sh

observability:
	docker compose -f $(COMPOSE_DEMO) -f $(COMPOSE_OBS) up -d --build

observability-down:
	docker compose -f $(COMPOSE_DEMO) -f $(COMPOSE_OBS) down

# ---------------------------------------------------------------------------
# GeoServer vector-data layer (opt-in — mcp-geo-server integration)
# ---------------------------------------------------------------------------
geoserver-up:
	docker compose -f $(COMPOSE_GEOSERVER) --profile geoserver up -d

geoserver-init:
	docker compose -f $(COMPOSE_GEOSERVER) --profile geoserver run --rm geoserver-init

geoserver-logs:
	docker compose -f $(COMPOSE_GEOSERVER) --profile geoserver logs -f

geoserver-down:
	docker compose -f $(COMPOSE_GEOSERVER) --profile geoserver down

# DTM tiles live in the /data folder shared with the GeoServer container.
GEOSERVER_DTM_DIR ?= ../mcp-geoserver/data/dtm

geoserver-sync:                # load IFFI + PAI from GeoServer PostGIS into the operational DB
	$(UV) run limen geoserver-sync

dtm-vrt:                       # build a virtual mosaic over the 5 m DTM tiles (needs host GDAL)
	gdalbuildvrt $(GEOSERVER_DTM_DIR)/dtm5m.vrt $(GEOSERVER_DTM_DIR)/*.tif
	@echo "Built $(GEOSERVER_DTM_DIR)/dtm5m.vrt — set LIMEN_DEM_RASTER to this path."

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------
test:
	$(UV) run pytest --cov=limen

test-unit:
	$(UV) run pytest tests/unit

test-integration:
	$(UV) run pytest tests/integration -m integration

test-frontend:
	cd frontend && npm run lint && npm test && npm run build

lint:
	$(UV) run ruff check src tests

format:
	$(UV) run ruff format src tests

typecheck:
	$(UV) run mypy

check: lint typecheck test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
