# Build per Anthropic OSS Scanner (https://github.com/anthropics/oss-scanner).
#
# Il contesto è la radice del repository. La rete c'è solo durante questa
# build: dopo, lo scanner lavora offline, quindi qui si scarica tutto quello
# che servirà ai test — l'ambiente Python di tutti i gruppi (come la CI), le
# dipendenze della SPA, e un PostgreSQL 15 + PostGIS locale al posto del
# container che testcontainers avvierebbe (senza Docker né rete non partirebbe).
#
# Dentro l'immagine:
#   pg_ctlcluster 15 main start
#   uv run pytest tests/unit
#   uv run pytest tests/integration      # usa LIMEN_TEST_DATABASE_URL
#   cd frontend && npx vitest run
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system \
    UV_NO_PROGRESS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential git ca-certificates \
      libgdal-dev gdal-bin libgeos-dev libproj-dev proj-bin \
      postgresql-15 postgresql-15-postgis-3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# scanner contract: the checkout lives inside the image, at /src
COPY . /src
WORKDIR /src

RUN uv sync --frozen --all-groups
RUN cd frontend && npm ci --no-audit --no-fund && npm run build

# Il database dei test, come l'immagine postgis/postgis che testcontainers
# avvierebbe: PostGIS già attivo, perché il pool registra il codec della
# geometria prima che le migrazioni (fixture `pg_pool`) girino.
RUN pg_ctlcluster 15 main start \
    && su postgres -c "psql -q -c \"CREATE ROLE limen LOGIN SUPERUSER PASSWORD 'limen'\"" \
    && for db in limen geodata; do \
         su postgres -c "createdb -O limen $db" \
         && su postgres -c "psql -q -d $db -c 'CREATE EXTENSION postgis'"; \
       done \
    && pg_ctlcluster 15 main stop

ENV UV_OFFLINE=1 \
    LIMEN_TEST_DATABASE_URL=postgresql://limen:limen@127.0.0.1:5432/limen \
    LIMEN_TEST_GEODATA_DATABASE_URL=postgresql://limen:limen@127.0.0.1:5432/geodata

# I test girano per verificare l'immagine, ma un rosso non ferma la build.
RUN uv run pytest tests/unit -q -p no:cacheprovider || echo "WARNING: unit tests reported failures"
RUN pg_ctlcluster 15 main start \
    && (uv run pytest tests/integration/test_repos.py -q -p no:cacheprovider \
        || echo "WARNING: integration tests reported failures") \
    ; pg_ctlcluster 15 main stop
RUN cd frontend && (npx vitest run || echo "WARNING: frontend tests reported failures")
