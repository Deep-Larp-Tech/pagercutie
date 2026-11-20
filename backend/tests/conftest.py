from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from pagercutie.core.db import create_engine, get_session, get_sessionmaker
from pagercutie.core.settings import Settings
from pagercutie.main import create_app

BACKEND_DIR = Path(__file__).parents[1]

type ClientFactory = Callable[[Settings], AbstractAsyncContextManager[AsyncClient]]


def migrate(database_url: str) -> None:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def database_url(postgres: PostgresContainer) -> str:
    url = postgres.get_connection_url()
    migrate(url)
    return url


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
