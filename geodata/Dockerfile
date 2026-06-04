# Limen Geo-Data Service — small image, NO datasets baked in.
#
# Three build stages:
#   1. `tippecanoe-builder` — compiles the felt/tippecanoe binary from
#      source (apt's Debian bookworm doesn't ship a tippecanoe package).
#   2. `py-builder`         — installs the Python venv via uv.
#   3. runtime              — Python + GDAL/PROJ libs + tippecanoe binary
#                             copied from stage 1 + the venv from stage 2.
#
# The image carries the Python code, the GDAL/pyogrio stack, and the
# tippecanoe CLI. Datasets land in the named Postgres volume at first
# `limen geodata init`; the image stays well under 1 GB.
#
# Build from the monorepo root so the `limen` package + the
# `limen-geodata` workspace member are both visible:
#
#   docker build -f geodata/Dockerfile -t limen/geodata:0.1 .

# ---------------------------------------------------------------------------
# Stage 1 — compile tippecanoe from source (felt/tippecanoe is the
# actively-maintained fork after Mapbox archived the upstream repo).
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS tippecanoe-builder

ARG TIPPECANOE_REF=2.50.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        g++ \
        git \
        libsqlite3-dev \
        make \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${TIPPECANOE_REF}" \
        https://github.com/felt/tippecanoe.git /src/tippecanoe \
    && cd /src/tippecanoe \
    && make -j"$(nproc)" \
    && make install PREFIX=/opt/tippecanoe

# ---------------------------------------------------------------------------
# Stage 2 — install Python deps with uv into a virtualenv we can copy.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS py-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        libgdal-dev \
        libgeos-dev \
        libproj-dev \
        libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -s /root/.local/bin/uv /usr/local/bin/uv

# Build at /app so the venv's console-script shebangs point at
# /app/.venv/bin/python — the same path we COPY the venv into in the
# runtime stage. (uv writes absolute shebangs by default; aligning the
# build WORKDIR with the runtime one is simpler than post-processing.)
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY geodata ./geodata
RUN uv sync --frozen --no-dev --group mcp

# ---------------------------------------------------------------------------
# Stage 3 — runtime image. Python + GDAL/PROJ + tippecanoe binary + venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgdal32 \
        libgeos-c1v5 \
        libproj25 \
        libsqlite3-0 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash geodata

# Tippecanoe binaries from stage 1.
COPY --from=tippecanoe-builder /opt/tippecanoe/bin/tippecanoe /usr/local/bin/tippecanoe
COPY --from=tippecanoe-builder /opt/tippecanoe/bin/tile-join /usr/local/bin/tile-join

WORKDIR /app
COPY --from=py-builder /app/.venv /app/.venv
COPY --from=py-builder /app/src /app/src
COPY --from=py-builder /app/geodata /app/geodata
COPY pyproject.toml /app/pyproject.toml

# Volumes wired by docker-compose; mkdir so non-root user can write.
RUN mkdir -p /var/lib/geodata/geojson /var/lib/geodata/pmtiles \
    && chown -R geodata:geodata /var/lib/geodata

USER geodata

# Default command is the init job; the MCP service overrides via compose.
ENTRYPOINT ["limen"]
CMD ["geodata", "init"]
