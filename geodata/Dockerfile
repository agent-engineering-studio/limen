# Limen Geo-Data Service — small image, NO datasets baked in.
#
# The image carries the Python code, the GDAL/pyogrio stack, and the
# tippecanoe CLI used by `limen geodata make-pmtiles`. Datasets land
# in the named Postgres volume at first `limen geodata init`; the
# image stays well under 1 GB even though the data it eventually
# orchestrates is multi-GB.
#
# Build from the monorepo root so the `limen` package + the
# `limen-geodata` workspace member are both visible:
#
#   docker build -f geodata/Dockerfile -t limen/geodata:0.1 .

# ---------------------------------------------------------------------------
# Builder — install Python deps with uv into a virtualenv we can copy.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

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

WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY geodata ./geodata
RUN uv sync --frozen --no-dev --extra mcp

# ---------------------------------------------------------------------------
# Runtime — Python + GDAL/PROJ libs + tippecanoe (apt) + the venv.
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
        tippecanoe \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash geodata

WORKDIR /app
COPY --from=builder /build/.venv /app/.venv
COPY --from=builder /build/src /app/src
COPY --from=builder /build/geodata /app/geodata
COPY pyproject.toml /app/pyproject.toml

# Volumes wired by docker-compose; mkdir so non-root user can write.
RUN mkdir -p /var/lib/geodata/geojson /var/lib/geodata/pmtiles \
    && chown -R geodata:geodata /var/lib/geodata

USER geodata

# Default command is the init job; the MCP service overrides via compose.
ENTRYPOINT ["limen"]
CMD ["geodata", "init"]
