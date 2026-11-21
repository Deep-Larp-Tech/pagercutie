import asyncio

import structlog

log = structlog.get_logger("dedup")


async def flush_counters(stopping: asyncio.Event) -> None:
    """Add the occurrence counters from Redis to the alert rows every 5 s (SPEC §9)."""
    log.info("dedup.flush_started", message="Counter flush started; flushing is not implemented yet")
    await stopping.wait()
