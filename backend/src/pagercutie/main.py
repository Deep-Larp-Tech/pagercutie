import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from larper.core.db import create_engine, create_sessionmaker
from larper.core.errors import DomainError, error_body
from larper.core.log import configure_logging, request_logging_middleware
from larper.core.settings import Settings, get_settings
from larper.core.telemetry import configure_telemetry
from larper.events.router import router as events_router
from larper.health.router import router as health_router
from larper.imports.router import router as imports_router
from larper.persons.router import router as persons_router
from larper.skills.router import router as skills_router

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

    app = FastAPI(title="larp-stack", lifespan=lifespan, generate_unique_id_function=operation_id)
    app.state.settings = settings
    app.state.sessionmaker = create_sessionmaker(engine)

    app.add_exception_handler(DomainError, handle_domain_error)
    app.middleware("http")(request_logging_middleware)

    app.include_router(health_router)
    app.include_router(persons_router)
    app.include_router(skills_router)
    app.include_router(events_router)
    app.include_router(imports_router)

    if telemetry:
        telemetry.instrument(app, engine)
    return app
