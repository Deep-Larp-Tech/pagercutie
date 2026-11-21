# Seed and load generator for the demo (demo/compose.yaml). Build context is demo/.
FROM python:3.14-slim

# iproute2 provides `tc` for the netem delay in load.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
# The versions backend/uv.lock pins.
RUN pip install --no-cache-dir httpx==0.28.1 websockets==17.4

WORKDIR /demo
COPY seed.py load.py probe.py load.sh ./
COPY runbooks ./runbooks
RUN chmod +x load.sh
