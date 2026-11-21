# syntax=docker/dockerfile:1
# Build from the repo root: docker build -f frontend/Dockerfile .
# Node and pnpm versions come from mise.toml, not from this file.

ARG MISE_VERSION=2026.11.10
ARG DEBIAN=trixie-slim
ARG CADDY=2.11-alpine

FROM jdxcode/mise:${MISE_VERSION} AS mise

# --- Toolchain: rebuilt only when mise.toml changes ------------------------------------------------
FROM debian:${DEBIAN} AS toolchain
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=mise /usr/local/bin/mise /usr/local/bin/mise
ENV MISE_DATA_DIR=/mise \
    MISE_CONFIG_DIR=/mise \
    MISE_CACHE_DIR=/mise/cache \
    PATH=/mise/shims:$PATH
WORKDIR /app
COPY mise.toml ./
RUN mise trust /app/mise.toml \
    && mise install node pnpm

# --- Dependencies: rebuilt only when the lockfile or a package.json changes ------------------------
FROM toolchain AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Every workspace manifest, so the frozen lockfile matches; only the frontend's deps get installed.
COPY frontend/package.json frontend/
COPY e2e/package.json e2e/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm-store \
    pnpm install --frozen-lockfile --prefer-offline --filter frontend --store-dir /pnpm-store

# --- Build: rebuilt on source changes, reuses everything above -------------------------------------
FROM deps AS build
COPY frontend/ frontend/
RUN pnpm --filter frontend build

# --- Runtime: static files served by Caddy, which also proxies /api to the backend -----------------
FROM caddy:${CADDY} AS runtime
# The official image runs as root; Caddy only needs its data/config dirs to be writable.
RUN adduser -S -D -H -u 10001 web && chown -R web /data /config
ENV BACKEND_URL=http://api:8000
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/frontend/dist /srv
USER web
EXPOSE 8080
