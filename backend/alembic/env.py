import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  (register models)
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
