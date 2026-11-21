"""Prints the median round trip of `GET {base_url}/health`, so the entrypoint can show the added network delay."""

import os
import statistics
import sys
import time

import httpx


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DEMO_BASE_URL", "http://localhost:5173/api")
    samples = []
    with httpx.Client(base_url=base_url, timeout=10) as client:
        client.get("/health")
        for _ in range(10):
            started = time.perf_counter()
            client.get("/health").raise_for_status()
            samples.append((time.perf_counter() - started) * 1000)
    print(f"{statistics.median(samples):.1f} ms")


if __name__ == "__main__":
    main()
