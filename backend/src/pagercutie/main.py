import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import exc as sqlalchemy_errors

from pagercutie.alerts.router import deliveries_router
from pagercutie.alerts.router import me_router as alerts_me_router
from pagercutie.alerts.router import router as alerts_router
from pagercutie.audit.router import router as audit_router
from pagercutie.auth.router import router as auth_router
from pagercutie.core.broadcast import Broadcast
from pagercutie.core.db import NotifyChannel, PoolLimits, create_engine, create_sessionmaker
from pagercutie.core.errors import DomainError, Overloaded, error_body, retry_after
from pagercutie.core.listen import listen_worker
from pagercutie.core.log import configure_logging, request_logging_middleware
from pagercutie.core.redis import create_redis
from pagercutie.core.settings import Settings, get_settings
from pagercutie.core.telemetry import configure_telemetry
from pagercutie.core.workers import Worker, run_workers
from pagercutie.event_schemas.router import router as event_schemas_router
from pagercutie.health.router import router as health_router
from pagercutie.pipeline.adapters import ADAPTERS
from pagercutie.pipeline.admission import Admission
from pagercutie.pipeline.dedup import worker as dedup
from pagercutie.pipeline.dedup.windows import RedisWindowStore
from pagercutie.pipeline.dispatch.channels import build_adapters
from pagercutie.pipeline.dispatch.throttle import RedisThrottle
from pagercutie.pipeline.dispatch.worker import DispatchContext, dispatch_worker
from pagercutie.pipeline.executor import actions
from pagercutie.pipeline.executor import worker as executor
from pagercutie.pipeline.ingest.stage import SchemaCache, team_schema_query
from pagercutie.pipeline.state import IngestState, catalog_reloader, rule_set_reloader, schema_invalidator
from pagercutie.rules.router import router as rules_router
from pagercutie.runbooks.router import router as runbooks_router
from pagercutie.sources.router import router as sources_router
from pagercutie.teams.router import router as teams_router
from pagercutie.users.router import router as users_router
from pagercutie.users.service import bootstrap_admin

log = structlog.get_logger("http")

# Seconds a client should wait after a request found no free database connection (SPEC §5.1).
POOL_TIMEOUT_RETRY_AFTER_S = 1


def operation_id(route: APIRoute) -> str:
    return route.name


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise exc
    log.info("http.domain_error", message=str(exc), error=type(exc).__name__, path=request.url.path)
    status_code, detail = error_body(exc)
    seconds = retry_after(exc)
    headers = None if seconds is None else {"Retry-After": str(seconds)}
    return JSONResponse({"detail": detail}, status_code=status_code, headers=headers)


async def handle_pool_timeout(request: Request, exc: Exception) -> JSONResponse:
    """A request that waited `db_pool_timeout_seconds` for a connection answers 503 instead of 500 (SPEC §5.1)."""
    if not isinstance(exc, sqlalchemy_errors.TimeoutError):
        raise exc
    log.warning("http.pool_timeout", message="No database connection free", path=request.url.path)
    return await handle_domain_error(
        request, Overloaded("No database connection is free on this replica", POOL_TIMEOUT_RETRY_AFTER_S)
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    telemetry = configure_telemetry(settings)
    configure_logging(settings, telemetry.logger_provider if telemetry else None)
    # Requests and background loops get separate pools, so neither can starve the other (ADR-0110).
    engine = create_engine(
        settings.database_url,
        PoolLimits(settings.db_pool_size, settings.db_pool_max_overflow, settings.db_pool_timeout_seconds),
    )
    sessionmaker = create_sessionmaker(engine)
    worker_engine = create_engine(
        settings.database_url,
        PoolLimits(
            settings.db_worker_pool_size,
            settings.db_worker_pool_max_overflow,
            settings.db_worker_pool_timeout_seconds,
        ),
    )
    worker_sessionmaker = create_sessionmaker(worker_engine)
    redis = create_redis(settings.redis_url)
    http_client = actions.create_http_client()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if settings.bootstrap_admin_email:
            async with sessionmaker() as session, session.begin():
                await bootstrap_admin(session, settings.bootstrap_admin_email)
        async with run_workers(workers):
            yield
        await redis.aclose()
        await http_client.aclose()
        await engine.dispose()
        await worker_engine.dispose()
        if telemetry:
            await asyncio.to_thread(telemetry.shutdown)

    app = FastAPI(
        title="pagercutie",
        lifespan=lifespan,
        generate_unique_id_function=operation_id,
        separate_input_output_schemas=False,
    )
    app.state.settings = settings
    app.state.sessionmaker = sessionmaker
    app.state.redis = redis
    app.state.admission = Admission.from_settings(settings, redis)
    windows = RedisWindowStore(redis)
    app.state.windows = windows
    ingest_state = IngestState(
        sessionmaker=sessionmaker, window_store=windows, schemas=SchemaCache(team_schema_query(sessionmaker))
    )
    app.state.ingest = ingest_state
    alert_changes = Broadcast()
    app.state.alert_changes = alert_changes
    dispatch_context = DispatchContext(
        sessionmaker=worker_sessionmaker,
        adapters=build_adapters(settings, worker_sessionmaker),
        throttle=RedisThrottle(redis, settings.throttle_capacity, settings.throttle_refill_seconds),
        settings=settings,
        wake=asyncio.Event(),
    )

    async def wake_dispatch() -> None:
        dispatch_context.wake.set()

    wake_executor = asyncio.Event()

    reload_rules = rule_set_reloader(ingest_state)
    listener = listen_worker(
        worker_engine,
        {
            NotifyChannel.SOURCES_CHANGED: catalog_reloader(ingest_state),
            NotifyChannel.SCHEMAS_CHANGED: schema_invalidator(ingest_state),
            NotifyChannel.RULES_CHANGED: reload_rules,
            NotifyChannel.ACCESS_CHANGED: reload_rules,
            NotifyChannel.ALERT_CHANGED: alert_changes,
            NotifyChannel.DELIVERIES_PENDING: wake_dispatch,
            NotifyChannel.STEPS_PENDING: executor.steps_pending_handler(wake_executor),
        },
        ingest_state.drop_caches,
    )
    integrations = actions.Integrations(http=actions.HttpxClient(http_client), ops=actions.SimulatedOps())
    workers = [
        dispatch_worker(dispatch_context),
        Worker(name="counter-flush", run=dedup.counter_flush(worker_sessionmaker, windows)),
        Worker(
            name="executor",
            run=executor.executor_loop(
                worker_sessionmaker, integrations, wake_executor, executor.ExecutorConfig.from_settings(settings)
            ),
        ),
        listener,
    ]

    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(sqlalchemy_errors.TimeoutError, handle_pool_timeout)
    app.middleware("http")(request_logging_middleware)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(teams_router)
    app.include_router(sources_router)
    app.include_router(event_schemas_router)
    app.include_router(rules_router)
    app.include_router(runbooks_router)
    app.include_router(alerts_router)
    app.include_router(alerts_me_router)
    app.include_router(deliveries_router)
    app.include_router(audit_router)
    for adapter in ADAPTERS:
        app.include_router(adapter.router())

    if telemetry:
        telemetry.instrument(app, [engine, worker_engine], redis)
    return app
