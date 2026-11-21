import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from pagercutie.alerts import service as alerts_service
from pagercutie.alerts.schemas import AlertEventType
from pagercutie.core.db import create_engine, get_session, get_sessionmaker
from pagercutie.core.settings import Settings
from pagercutie.main import create_app
from pagercutie.pipeline.executor import stage as executor_stage

BACKEND_DIR = Path(__file__).parents[1]

type ClientFactory = Callable[[Settings], AbstractAsyncContextManager[AsyncClient]]

type AlertChanges = list[tuple[uuid.UUID, AlertEventType]]


def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


def migrate(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:8-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    return f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def database_url(postgres: PostgresContainer) -> str:
    url = postgres.get_connection_url()
    migrate(url)
    return url


@pytest.fixture
def make_alembic_config() -> Callable[[str], Config]:
    return alembic_config


@pytest.fixture(scope="session")
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url)


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessionmaker(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessions on one connection whose outer transaction is rolled back; their commits only release savepoints."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        yield async_sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        await transaction.rollback()


@pytest.fixture
def alert_changes(monkeypatch: pytest.MonkeyPatch) -> AlertChanges:
    """The `alert_changed` notifications that step decisions and the executor send, in order; Postgres would deliver
    them only on commit, which the `session` fixture never does."""
    sent: AlertChanges = []

    async def record_change(_session: AsyncSession, alert_id: uuid.UUID, change: AlertEventType) -> None:
        sent.append((alert_id, change))

    monkeypatch.setattr(alerts_service, "notify_alert_changed", record_change)
    monkeypatch.setattr(executor_stage, "notify_alert_changed", record_change)
    return sent


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as session:
        yield session


@pytest.fixture
def make_client(session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]) -> ClientFactory:
    @asynccontextmanager
    async def factory(settings: Settings) -> AsyncGenerator[AsyncClient]:
        app = create_app(settings)

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        app.dependency_overrides[get_sessionmaker] = lambda: sessionmaker
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    return factory


@pytest.fixture
async def client(make_client: ClientFactory, settings: Settings) -> AsyncIterator[AsyncClient]:
    async with make_client(settings) as client:
        yield client
