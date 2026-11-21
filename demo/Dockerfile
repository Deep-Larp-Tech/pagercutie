FROM python:3.14-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir httpx==0.28.1 websockets==17.4

WORKDIR /demo
COPY seed.py load.py probe.py load.sh ./
COPY runbooks ./runbooks
RUN chmod +x load.sh
