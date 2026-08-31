"""Alembic runtime that binds migrations to PayLens SQLAlchemy metadata."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from app.persistence.database import Base, database_url_from_environment

load_dotenv()
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
database_url = database_url_from_environment()
if database_url:
    # ConfigParser treats percent signs as interpolation markers. Escaping them
    # preserves URL-encoded credentials such as ``%40`` when Alembic reads back
    # the SQLAlchemy URL.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Render migration SQL without opening a database connection."""
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations through a short-lived, non-pooled database connection."""
    connectable = engine_from_config(config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


# Alembic selects offline mode for SQL generation and online mode for normal upgrades.
run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
