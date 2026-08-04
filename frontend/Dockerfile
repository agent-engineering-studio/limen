# Limen frontend — static SPA image.
#
# Builds the Vite bundle and serves it with nginx. The API image
# (`infra/docker/Dockerfile.api`) does NOT serve the frontend, so this is what
# puts the map on a real hostname.
#
# The deployment path prefix is a BUILD argument, not a runtime one: Vite
# rewrites every asset URL at build time. Pass `BASE_PATH=/limen/` to serve the
# app under `https://host/limen/`, or leave the default `/` for a dedicated
# host. This keeps `vite.config.ts` free of any deployment-specific value.
#
#   docker build -t limen-web \
#     --build-arg BASE_PATH=/limen/ \
#     --build-arg VITE_API_URL=https://example.org/limen \
#     --build-arg VITE_TILESERV_URL=https://example.org/limen/tiles \
#     frontend
#
# VITE_API_URL is the application ROOT, not the `/api` prefix: `ApiClient`
# concatenates paths that already start with `/api`.

# ---------------------------------------------------------------------------
# Stage 1 — build the bundle
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS build

WORKDIR /app

# Dependencies first: only a lockfile change invalidates this layer.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG BASE_PATH=/
ARG VITE_API_URL
ARG VITE_TILESERV_URL
ARG VITE_PAI_PMTILES_URL
ARG VITE_IFFI_PMTILES_URL
ENV VITE_API_URL=$VITE_API_URL \
    VITE_TILESERV_URL=$VITE_TILESERV_URL \
    VITE_PAI_PMTILES_URL=$VITE_PAI_PMTILES_URL \
    VITE_IFFI_PMTILES_URL=$VITE_IFFI_PMTILES_URL

# `vite build` directly rather than `npm run build`, which also runs `tsc -b`:
# type-checking belongs to CI, and a deploy build should not fail on a type
# error that does not affect the emitted bundle.
RUN npx vite build --base="$BASE_PATH"

# ---------------------------------------------------------------------------
# Stage 2 — serve
# ---------------------------------------------------------------------------
FROM nginx:alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, NOT localhost: in this image localhost resolves to ::1 only,
# while nginx listens on IPv4 — the probe would fail forever, and an
# unhealthy container is dropped by service discovery.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/healthz > /dev/null || exit 1
