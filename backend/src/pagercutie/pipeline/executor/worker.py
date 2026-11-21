import asyncio

import structlog

log = structlog.get_logger("executor")


async def run(stopping: asyncio.Event) -> None:
    """Claim, run and complete due step runs (SPEC §11.3)."""
    log.info("executor.started", message="Executor started; runbook step execution is not implemented yet")
    await stopping.wait()
