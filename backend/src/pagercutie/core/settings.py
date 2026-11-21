from datetime import timedelta
from functools import lru_cache

from pydantic import AnyHttpUrl, EmailStr, Field
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

    # Local default: the Mailpit from compose.yaml. Email deliveries go through this SMTP server (SPEC §10).
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, gt=0, le=65535)
    smtp_from: EmailStr = "pagercutie@example.com"

    # Per-user token bucket for external channels, shared through Redis (SPEC §5.2): `capacity` messages at once,
    # then one more every `refill_seconds`.
    throttle_capacity: int = Field(default=5, gt=0)
    throttle_refill_seconds: float = Field(default=12.0, gt=0)

    # How long a dispatcher owns a claimed delivery before another replica may send it again (SPEC §10).
    delivery_lease_seconds: int = Field(default=30, gt=0)
    delivery_batch_size: int = Field(default=50, gt=0)

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
