import asyncio

import structlog

log = structlog.get_logger("dispatch")


async def run(stopping: asyncio.Event) -> None:
    """Claim, send and complete due deliveries; wakes on `NOTIFY deliveries_pending` (SPEC §10)."""
    log.info("dispatch.started", message="Dispatcher started; sending deliveries is not implemented yet")
    await stopping.wait()
