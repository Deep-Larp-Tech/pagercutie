# syntax=docker/dockerfile:1

ARG MISE_VERSION=2026.11.10
ARG DEBIAN=trixie-slim
ARG CADDY=2.11-alpine

FROM jdxcode/mise:${MISE_VERSION} AS mise

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

FROM toolchain AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json frontend/
COPY e2e/package.json e2e/
RUN --mount=type=cache,id=pnpm-store,target=/pnpm-store \
    pnpm install --frozen-lockfile --prefer-offline --filter frontend --store-dir /pnpm-store

FROM deps AS build
COPY frontend/ frontend/
RUN pnpm --filter frontend build

FROM caddy:${CADDY} AS runtime
RUN adduser -S -D -H -u 10001 web && chown -R web /data /config
ENV BACKEND_HOST=backend
COPY frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/frontend/dist /srv
USER web
EXPOSE 8080
