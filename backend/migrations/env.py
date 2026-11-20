import asyncio
from logging.config import fileConfig
from typing import Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from pagercutie.alerts import models as alerts_models
from pagercutie.audit import models as audit_models
from pagercutie.auth import models as auth_models
from pagercutie.core.models import Base, PydanticJSONB
from pagercutie.core.settings import get_settings
from pagercutie.event_schemas import models as event_schemas_models
from pagercutie.rules import models as rules_models
from pagercutie.runbooks import models as runbooks_models
from pagercutie.sources import models as sources_models
from pagercutie.teams import models as teams_models
from pagercutie.users import models as users_models

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Only when run as the `alembic` CLI: called from code (tests, app), the caller's logging setup stays in charge.
# disable_existing_loggers=False: the default would silently mute loggers like uvicorn.error and sqlalchemy.*.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Import every entity's models module above (and list it here) so its tables register on Base.metadata.
_ = (
    alerts_models,
    audit_models,
    auth_models,
    event_schemas_models,
    rules_models,
    runbooks_models,
    sources_models,
    teams_models,
    users_models,
)
target_metadata = Base.metadata

# One source of truth for the URL: tests pass it via `config.attributes`, everything else reads Settings.
database_url: str = config.attributes.get("database_url") or get_settings().database_url

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def render_item(type_: str, obj: object, autogen_context: AutogenContext) -> str | Literal[False]:
    """Render DTO-typed jsonb columns as plain `JSONB`: migrations must not import application types."""
    if type_ == "type" and isinstance(obj, PydanticJSONB):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB(astext_type=sa.Text())"
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        render_item=render_item,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_item=render_item)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        {"sqlalchemy.url": database_url},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
