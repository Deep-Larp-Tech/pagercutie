from functools import lru_cache

from pydantic import AnyHttpUrl, PositiveInt
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

    log_level: str = "INFO"
    log_json: bool = False

    otel_enabled: bool = False
    otel_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:4318")
    otel_service_name: str = "pagercutie-backend"

    import_max_bytes: PositiveInt = 5 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate({})
