import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool

from pagercutie.core.db import POOL_RECYCLE_S, create_engine
from pagercutie.core.settings import Settings

pytestmark = pytest.mark.anyio


async def test_engine_keeps_a_fixed_pool_without_pre_ping() -> None:
    engine = create_engine(Settings(db_pool_size=7, db_max_overflow=2))
    pool = engine.pool

    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == 7
    assert pool._max_overflow == 2
    assert pool._recycle == POOL_RECYCLE_S
    assert pool._pre_ping is False
    await engine.dispose()
