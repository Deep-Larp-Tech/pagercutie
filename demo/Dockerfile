# Seed and load generator for the demo (demo/compose.yaml). Build context is the repo root, for the generated
# gRPC ingest messages.
FROM python:3.14-slim

# iproute2 provides `tc` for the netem delay in load.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
# The versions backend/uv.lock pins.
RUN pip install --no-cache-dir httpx==0.28.1 websockets==17.4 grpcio==1.85.3 protobuf==7.36.2

WORKDIR /demo
COPY backend/src/pagercutie/v1/ingest_pb2.py pagercutie/v1/
COPY demo/seed.py demo/load.py demo/probe.py demo/load.sh ./
RUN chmod +x load.sh
