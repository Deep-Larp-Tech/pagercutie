from datetime import timedelta
from functools import lru_cache

from pydantic import AnyHttpUrl, EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Local default: the Redis from compose.yaml. Shared state of all replicas: dedup windows, throttles (SPEC §5).
    redis_url: str = "redis://localhost:6379/0"

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
