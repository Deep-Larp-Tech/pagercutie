# syntax=docker/dockerfile:1
# Build from the repo root: docker build -f backend/Dockerfile .
# Python and uv versions come from mise.toml, not from this file.

ARG MISE_VERSION=2026.11.10
ARG DEBIAN=trixie-slim

FROM jdxcode/mise:${MISE_VERSION} AS mise

# --- Toolchain: rebuilt only when mise.toml changes ------------------------------------------------
FROM debian:${DEBIAN} AS toolchain
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=mise /usr/local/bin/mise /usr/local/bin/mise
ENV MISE_DATA_DIR=/mise \
    MISE_CONFIG_DIR=/mise \
    MISE_CACHE_DIR=/mise/cache \
    PATH=/mise/shims:$PATH
WORKDIR /app
COPY mise.toml ./
# The interpreter is copied to a fixed path, so the venv and the runtime image never depend on mise's layout.
RUN mise trust /app/mise.toml \
    && mise install python uv \
    && cp -a "$(mise where python)" /opt/python

# --- Dependencies: rebuilt only when the lockfile changes ------------------------------------------
FROM toolchain AS deps
ENV UV_PYTHON=/opt/python/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# --- Application: rebuilt on code changes, reuses everything above ---------------------------------
FROM deps AS build
COPY backend/README.md ./
COPY backend/src ./src
# Non-editable: the package lands in site-packages, so the runtime image needs no sources.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- Runtime: interpreter + venv + migrations, no mise, uv or build caches -------------------------
FROM debian:${DEBIAN} AS runtime
RUN useradd --system --uid 10001 --no-create-home pagercutie
WORKDIR /app
COPY --from=build /opt/python /opt/python
COPY --from=build /app/.venv /app/.venv
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
USER pagercutie
# 8000: HTTP (API, webhook and WebSocket ingest); 50051: gRPC ingest (ADR-0099).
EXPOSE 8000 50051
CMD ["uvicorn", "pagercutie.asgi:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
