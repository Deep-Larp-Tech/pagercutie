import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool

from pagercutie.core.db import POOL_RECYCLE_S, PoolLimits, create_engine
from pagercutie.core.settings import Settings

pytestmark = pytest.mark.anyio


async def test_engine_uses_the_pool_limits_without_pre_ping() -> None:
    engine = create_engine("postgresql+asyncpg://u:p@127.0.0.1:1/db", PoolLimits(size=7, max_overflow=2, timeout_s=3))
    pool = engine.pool

    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == 7
    assert pool._max_overflow == 2
    assert pool._timeout == 3
    assert pool._recycle == POOL_RECYCLE_S
    assert pool._pre_ping is False
    await engine.dispose()


def test_default_pools_keep_every_connection_open() -> None:
    settings = Settings.model_validate({})

    assert (settings.db_pool_size, settings.db_pool_max_overflow) == (15, 0)
    assert (settings.db_worker_pool_size, settings.db_worker_pool_max_overflow) == (20, 0)
