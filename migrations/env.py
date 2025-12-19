from __future__ import annotations

from logging.config import fileConfig
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(BASE_DIR / "src"))

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import Base, DATABASE_URL

# this is the Alembic Config object, which provides
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
