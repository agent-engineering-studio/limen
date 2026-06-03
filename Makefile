# Limen — developer Makefile

UV ?= uv
COMPOSE_FILE := infra/docker/docker-compose.dev.yml

.PHONY: help install up-dev down-dev logs seed migrate test test-unit test-integration lint format typecheck check clean

help:
	@echo "Limen — common developer targets"
	@echo ""
	@echo "  make install            install runtime + dev deps via uv"
	@echo "  make up-dev             start local Postgres+PostGIS (Docker compose)"
	@echo "  make down-dev           stop local Postgres+PostGIS"
	@echo "  make logs               tail Postgres container logs"
	@echo "  make migrate            apply pending SQL migrations"
	@echo "  make seed               apply migrations + seed Puglia/Basilicata AOIs + grids"
	@echo "  make test               run all tests"
	@echo "  make test-unit          run unit tests only"
	@echo "  make test-integration   run integration tests (needs Docker)"
	@echo "  make lint               ruff check"
	@echo "  make format             ruff format"
	@echo "  make typecheck          mypy --strict on src/"
	@echo "  make check              lint + typecheck + tests"
	@echo "  make clean              remove caches and build artefacts"

install:
	$(UV) sync --all-groups

up-dev:
	docker compose -f $(COMPOSE_FILE) up -d --build

down-dev:
	docker compose -f $(COMPOSE_FILE) down

logs:
	docker compose -f $(COMPOSE_FILE) logs -f postgres

migrate:
	$(UV) run limen migrate

seed:
	$(UV) run limen seed

test:
	$(UV) run pytest

test-unit:
	$(UV) run pytest tests/unit

test-integration:
	$(UV) run pytest tests/integration -m integration

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
