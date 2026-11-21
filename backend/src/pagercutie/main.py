import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import assert_never

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from pagercutie.alerts.router import me_router as alerts_me_router
from pagercutie.alerts.router import router as alerts_router
from pagercutie.audit.router import router as audit_router
from pagercutie.auth.router import router as auth_router
from pagercutie.core.broker import consumer_worker, open_producer
from pagercutie.core.db import create_engine, create_sessionmaker
from pagercutie.core.enums import Role
from pagercutie.core.errors import DomainError, error_body
from pagercutie.core.log import configure_logging, request_logging_middleware
from pagercutie.core.settings import Settings, get_settings
from pagercutie.core.telemetry import configure_telemetry
from pagercutie.core.workers import Worker, run_workers
from pagercutie.event_schemas.router import router as event_schemas_router
from pagercutie.health.router import router as health_router
from pagercutie.pipeline.dedup import consumer as dedup
from pagercutie.pipeline.dispatcher import consumer as dispatcher
from pagercutie.pipeline.evaluator import consumer as evaluator
from pagercutie.pipeline.executor import worker as executor
from pagercutie.rules.router import router as rules_router
from pagercutie.runbooks.router import router as runbooks_router
from pagercutie.sources.router import router as sources_router
from pagercutie.teams.router import router as teams_router
from pagercutie.users.router import router as users_router
from pagercutie.users.service import bootstrap_admin

log = structlog.get_logger("http")

# Roles that write to a topic and so open a producer.
PRODUCING_ROLES = frozenset({Role.INGEST, Role.EVALUATOR, Role.DEDUP})


def operation_id(route: APIRoute) -> str:
    return route.name


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    log.info("http.domain_error", message=str(exc), error=type(exc).__name__, path=request.url.path)
    status_code, detail = error_body(exc)
    return JSONResponse({"detail": detail}, status_code=status_code)


def include_management_api(app: FastAPI) -> None:
    """The REST API of docs/DOMAIN.md."""
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(teams_router)
    app.include_router(sources_router)
    app.include_router(event_schemas_router)
    app.include_router(rules_router)
    app.include_router(runbooks_router)
    app.include_router(alerts_router)
    app.include_router(alerts_me_router)
    app.include_router(audit_router)


def role_workers(app: FastAPI, settings: Settings) -> list[Worker]:
    """Adds each role's routes to `app` and returns its background loops (SPEC §3.2)."""
    workers: list[Worker] = []
    for role in sorted(settings.roles):
        match role:
            case Role.API:
                include_management_api(app)
            case Role.INGEST:
                pass  # Source adapters (ING-1) add their webhook routes here.
            case Role.EVALUATOR:
                workers.append(consumer_worker(settings, evaluator.SUBSCRIPTION))
            case Role.DEDUP:
                workers.append(consumer_worker(settings, dedup.SUBSCRIPTION))
            case Role.DISPATCHER:
                workers.append(consumer_worker(settings, dispatcher.SUBSCRIPTION))
            case Role.EXECUTOR:
                workers.append(Worker(name="executor", run=executor.run))
            case _:
                assert_never(role)
    return workers


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    telemetry = configure_telemetry(settings)
    configure_logging(settings, telemetry.logger_provider if telemetry else None)
    engine = create_engine(settings.database_url)
    sessionmaker = create_sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if Role.API in settings.roles and settings.bootstrap_admin_email:
            async with sessionmaker() as session, session.begin():
                await bootstrap_admin(session, settings.bootstrap_admin_email)
        # Exits in reverse: workers stop before the producer they write to is flushed.
        async with AsyncExitStack() as stack:
            if settings.roles & PRODUCING_ROLES:
                app.state.producer = await stack.enter_async_context(open_producer(settings))
            app.state.workers = await stack.enter_async_context(run_workers(workers))
            yield
        await engine.dispose()
        if telemetry:
            await asyncio.to_thread(telemetry.shutdown)

    app = FastAPI(
        title="pagercutie",
        lifespan=lifespan,
        generate_unique_id_function=operation_id,
        # One schema per model: the recursive rule AST would otherwise exist twice (`-Input` / `-Output`) in the client.
        separate_input_output_schemas=False,
    )
    app.state.settings = settings
    app.state.sessionmaker = sessionmaker

    app.add_exception_handler(DomainError, handle_domain_error)
    app.middleware("http")(request_logging_middleware)

    app.include_router(health_router)
    workers = role_workers(app, settings)

    if telemetry:
        telemetry.instrument(app, engine)
    return app
