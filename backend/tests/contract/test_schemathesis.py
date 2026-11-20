import pytest
import schemathesis
from fastapi import FastAPI
from schemathesis import Case
from schemathesis.specs.openapi.checks import allow_header_conformance, positive_data_acceptance
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from conftest import migrate
from larper.core.settings import Settings
from larper.main import create_app


@pytest.fixture(scope="module")
def contract_app(postgres: PostgresContainer) -> FastAPI:
    # Schemathesis commits real rows, so it gets its own database instead of the rolled-back test one.
    postgres.exec(["psql", "-U", postgres.username, "-d", postgres.dbname, "-c", "CREATE DATABASE contract"])
    url = make_url(postgres.get_connection_url()).set(database="contract").render_as_string(hide_password=False)
    migrate(url)

    app = create_app(Settings(database_url=url, log_level="WARNING"))
    # The sync ASGI client runs each request on a fresh event loop; pooled asyncpg connections can't follow.
    app.state.sessionmaker = async_sessionmaker(create_async_engine(url, poolclass=NullPool), expire_on_commit=False)
    return app


@pytest.fixture(scope="module")
def contract_schema(contract_app: FastAPI) -> schemathesis.BaseSchema:
    return schemathesis.openapi.from_asgi("/openapi.json", contract_app)


schema = schemathesis.pytest.from_fixture("contract_schema")


@schema.parametrize()
def test_api_honours_its_contract(case: Case) -> None:
    # Starlette answers OPTIONS on a path with only the first matching route's methods (`Allow: GET` on
    # /persons, which also has POST). A framework limitation, not ours: skip just that check.
    # Domain rules legitimately reject schema-valid data (future dates, unknown ids, duplicate names, file types).
    case.call_and_validate(excluded_checks=[allow_header_conformance, positive_data_acceptance])
