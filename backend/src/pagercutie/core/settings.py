import socket
from datetime import timedelta
from functools import lru_cache
from typing import Annotated, assert_never

from pydantic import AnyHttpUrl, BeforeValidator, EmailStr, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from pagercutie.core.enums import Role, RoleGroup


def roles_in(group: RoleGroup) -> frozenset[Role]:
    match group:
        case RoleGroup.WORKER:
            return frozenset({Role.EVALUATOR, Role.DEDUP, Role.DISPATCHER, Role.EXECUTOR})
        case RoleGroup.ALL:
            return frozenset(Role)
        case _:
            assert_never(group)


def parse_roles(value: object) -> object:
    """Accepts one role or role group name (`APP_ROLES=worker`, `--role=api`); other values pass to validation."""
    if not isinstance(value, str):
        return value
    if value in RoleGroup:
        return roles_in(RoleGroup(value))
    return frozenset({value})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        case_sensitive=False,
        extra="ignore",
    )

    # Local default: the Postgres from compose.yaml (`mise run up`). Containers and deployments set APP_DATABASE_URL.
    database_url: str = "postgresql+asyncpg://pagercutie:pagercutie@localhost:5432/pagercutie"
    port: int = 8000

    session_ttl: timedelta = timedelta(hours=12)
    # Off by default: Caddy serves plain HTTP locally (Caddyfile); deployments behind TLS set APP_SESSION_COOKIE_SECURE.
    session_cookie_secure: bool = False

    # `api` alone needs no broker, so tests and the contract export start without Redpanda.
    roles: Annotated[frozenset[Role], NoDecode, BeforeValidator(parse_roles)] = frozenset({Role.API})
    # Local default: the host listener of the Redpanda in compose.yaml. Containers use redpanda:9092.
    broker_bootstrap_servers: str = "localhost:19092"
    # Kafka static membership (`group.instance.id`, SPEC §5.4); must be unique per process within a consumer group.
    worker_id: str = Field(default_factory=socket.gethostname)

    log_level: str = "INFO"
    log_json: bool = False

    otel_enabled: bool = False
    otel_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:4318")
    otel_service_name: str = "pagercutie-backend"

    # NFR-4: the API creates this admin on start when no admin exists, so a fresh database has someone to log in as.
    bootstrap_admin_email: EmailStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate({})
