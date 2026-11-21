import asyncio
from datetime import timedelta
from http import HTTPStatus

import pytest
import schemathesis
from fastapi import FastAPI
from schemathesis import Case
from schemathesis.specs.openapi.checks import allow_header_conformance, positive_data_acceptance, unsupported_method
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from conftest import migrate
from pagercutie.auth import service as auth_service
from pagercutie.core.settings import Settings
from pagercutie.main import create_app
from pagercutie.users.models import User
from pagercutie.users.schemas import GlobalRole


async def log_in_admin(url: str) -> str:
    engine = create_async_engine(url, poolclass=NullPool)
    async with async_sessionmaker(engine)() as session, session.begin():
        session.add(User(email="contract@example.com", display_name="Contract", timezone="UTC", role=GlobalRole.ADMIN))
        await session.flush()
        token, _ = await auth_service.login(session, "contract@example.com", timedelta(days=1))
    await engine.dispose()
    return token


@pytest.fixture(scope="module")
def contract_url(postgres: PostgresContainer) -> str:
    postgres.exec(["psql", "-U", postgres.username, "-d", postgres.dbname, "-c", "CREATE DATABASE contract"])
    url = make_url(postgres.get_connection_url()).set(database="contract").render_as_string(hide_password=False)
    migrate(url)
    return url


@pytest.fixture(scope="module")
def session_token(contract_url: str) -> str:
    """An admin's `pc_session`, so requests reach the route instead of stopping at 401."""
    return asyncio.run(log_in_admin(contract_url))


@pytest.fixture(scope="module")
def contract_app(contract_url: str) -> FastAPI:
    url = contract_url
    app = create_app(Settings(database_url=url, log_level="WARNING"))
    app.state.sessionmaker = async_sessionmaker(create_async_engine(url, poolclass=NullPool), expire_on_commit=False)
    return app


@pytest.fixture(scope="module")
def contract_schema(contract_app: FastAPI) -> schemathesis.BaseSchema:
    return schemathesis.openapi.from_asgi("/openapi.json", contract_app)


schema = schemathesis.pytest.from_fixture("contract_schema")


@schema.parametrize()
def test_api_honours_its_contract(case: Case, session_token: str) -> None:
    if case.cookies and "pc_session" in case.cookies and case.path != "/auth/logout":
        case.cookies["pc_session"] = session_token
    response = case.call()
    if response.status_code == HTTPStatus.NOT_IMPLEMENTED:
        pytest.skip("contract-first stub, checked once implemented")
    case.validate_response(
        response, excluded_checks=[allow_header_conformance, positive_data_acceptance, unsupported_method]
    )
