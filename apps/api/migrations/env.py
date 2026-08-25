"""Alembic environment.

Two entry points share it:

- the CLI (`alembic upgrade head`), which builds its own async engine from
  `MECHA_DATABASE_URL`, the same setting the app reads, so the two can never
  drift onto different databases;
- the app at startup, which hands over a live connection through
  `config.attributes["connection"]` rather than opening a second one.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from mecha_api.config import DatabaseSettings
from mecha_api.tables import Base
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
injected_connection: Connection | None = config.attributes.get("connection")

# Only for CLI runs: `fileConfig` would otherwise replace the handlers
# `observability.configure()` just installed.
if injected_connection is None and config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# What `--autogenerate` diffs the database against.
target_metadata = Base.metadata


def _url() -> str:
    return DatabaseSettings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # SQLite can't ALTER most things; batch mode rewrites the table
        # instead. Harmless on backends that don't need it.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif injected_connection is not None:
    # Called from the app's startup, already inside the event loop.
    do_run_migrations(injected_connection)
else:
    asyncio.run(run_async_migrations())
