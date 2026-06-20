"""Entorno de migraciones de Alembic (motor async).

La URL de la base de datos y la metadata se toman de la aplicación, de modo que
las migraciones usan exactamente la misma configuración que el runtime.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Registra TODAS las tablas en Base.metadata para que `autogenerate` las detecte.
import app.models.registry  # noqa: F401
from alembic import context
from app.core.config import settings
from app.core.event_loop import new_event_loop
from app.models.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    raise NotImplementedError("El modo offline de Alembic no está soportado en este proyecto.")

asyncio.run(run_async_migrations(), loop_factory=new_event_loop)
