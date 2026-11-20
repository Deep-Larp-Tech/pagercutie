import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from pagercutie.alerts.router import router as alerts_router
from pagercutie.audit.router import router as audit_router
from pagercutie.auth.router import router as auth_router
from pagercutie.core.db import create_engine, create_sessionmaker
from pagercutie.core.errors import DomainError, error_body
from pagercutie.core.log import configure_logging, request_logging_middleware
from pagercutie.core.settings import Settings, get_settings
from pagercutie.core.telemetry import configure_telemetry
from pagercutie.event_schemas.router import router as event_schemas_router
from pagercutie.health.router import router as health_router
from pagercutie.rules.router import router as rules_router
from pagercutie.runbooks.router import router as runbooks_router
from pagercutie.sources.router import router as sources_router
from pagercutie.teams.router import router as teams_router
from pagercutie.users.router import router as users_router

log = structlog.get_logger("http")


def operation_id(route: APIRoute) -> str:
    return route.name


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    log.info("http.domain_error", message=str(exc), error=type(exc).__name__, path=request.url.path)
    status_code, detail = error_body(exc)
    return JSONResponse({"detail": detail}, status_code=status_code)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    telemetry = configure_telemetry(settings)
    configure_logging(settings, telemetry.logger_provider if telemetry else None)
    engine = create_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
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
    app.state.sessionmaker = create_sessionmaker(engine)

    app.add_exception_handler(DomainError, handle_domain_error)
    app.middleware("http")(request_logging_middleware)

    app.include_router(health_router)
    # Management API (docs/DOMAIN.md).
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(teams_router)
    app.include_router(sources_router)
    app.include_router(event_schemas_router)
    app.include_router(rules_router)
    app.include_router(runbooks_router)
    app.include_router(alerts_router)
    app.include_router(audit_router)

    if telemetry:
        telemetry.instrument(app, engine)
    return app
