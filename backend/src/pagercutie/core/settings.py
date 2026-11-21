from datetime import timedelta
from functools import lru_cache
from typing import Self

from pydantic import AnyHttpUrl, EmailStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Seconds of a delivery lease kept free of the send and the connection wait, for the claim and completion queries.
DELIVERY_LEASE_MARGIN_S = 5.0


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

    # How long a claimed step run stays invisible to other replicas (ADR-0008).
    executor_lease_seconds: int = Field(default=30, gt=0)
    # Longest one step action may take before it fails as timed out; with the worker pool timeout it must fit inside
    # the lease, so the outcome is written before another replica may claim the step (ADR-0106).
    executor_step_timeout_seconds: float = Field(default=20.0, gt=0)
    # Claims of one step run that may end without an outcome (an exception or a lost replica) before the executor fails
    # the step (ADR-0103).
    executor_step_max_errors: int = Field(default=5, gt=0)
    # Longest one channel adapter may take; a slower send is a transient failure. With the worker pool timeout it must
    # fit inside the lease, or another replica could send the delivery again while this one still waits (ADR-0110).
    delivery_send_timeout_seconds: float = Field(default=15.0, gt=0)

    # Connection pools of one replica (ADR-0107). Requests and background loops use separate engines, so neither can
    # starve the other. One replica opens at most the sum of the four sizes; compose.yaml sizes Postgres
    # `max_connections` for that sum times the replica count.
    db_pool_size: int = Field(default=10, gt=0)
    db_pool_max_overflow: int = Field(default=5, ge=0)
    # Seconds a request waits for a connection before it answers 503 with `Retry-After` (SPEC §5.1).
    db_pool_timeout_seconds: float = Field(default=2.0, gt=0)
    db_worker_pool_size: int = Field(default=10, gt=0)
    db_worker_pool_max_overflow: int = Field(default=10, ge=0)
    # Seconds a background loop waits for a connection; counted against the delivery lease.
    db_worker_pool_timeout_seconds: float = Field(default=5.0, gt=0)

    # Ingest admission control (ADR-0108): ingest requests in flight on one replica before it answers 503, and the
    # token bucket per source and credential before it answers 429.
    ingest_max_in_flight: int = Field(default=32, gt=0)
    ingest_source_burst: int = Field(default=1000, gt=0)
    ingest_source_rate_per_second: float = Field(default=500.0, gt=0)

    log_level: str = "INFO"
    log_json: bool = False

    otel_enabled: bool = False
    otel_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:4318")
    otel_service_name: str = "pagercutie-backend"

    # NFR-4: the API creates this admin on start when no admin exists, so a fresh database has someone to log in as.
    bootstrap_admin_email: EmailStr | None = None

    @model_validator(mode="after")
    def _send_fits_in_the_lease(self) -> Self:
        budget = self.delivery_send_timeout_seconds + self.db_worker_pool_timeout_seconds + DELIVERY_LEASE_MARGIN_S
        if budget > self.delivery_lease_seconds:
            raise ValueError(
                "delivery_send_timeout_seconds + db_worker_pool_timeout_seconds + "
                f"{DELIVERY_LEASE_MARGIN_S} s must not exceed delivery_lease_seconds "
                f"({budget} > {self.delivery_lease_seconds})"
            )
        return self

    @model_validator(mode="after")
    def _step_fits_in_the_lease(self) -> Self:
        budget = self.executor_step_timeout_seconds + self.db_worker_pool_timeout_seconds
        if budget >= self.executor_lease_seconds:
            raise ValueError(
                "executor_step_timeout_seconds + db_worker_pool_timeout_seconds must be less than "
                f"executor_lease_seconds ({budget} >= {self.executor_lease_seconds})"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate({})
