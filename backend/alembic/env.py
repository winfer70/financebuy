"""
env.py — Alembic migration environment for TickerTap.

DATABASE_URL environment variable is REQUIRED and must be set before running
any migration command.  The variable overrides the placeholder in alembic.ini
so that no real credentials ever need to be committed to the repository.

Usage:
    export DATABASE_URL=postgresql://user:password@host:5432/tickerTap
    alembic upgrade head

The async +asyncpg driver suffix is stripped automatically so that Alembic
(which uses synchronous SQLAlchemy) can connect without installing asyncpg.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

# ── DATABASE_URL resolution ───────────────────────────────────────────────────
# The env var is the single source of truth for credentials; alembic.ini only
# holds a non-functional placeholder.
env_url = os.getenv("DATABASE_URL")
if not env_url:
    print(
        "ERROR: DATABASE_URL environment variable is not set.\n"
        "Set it before running Alembic, e.g.:\n"
        "  export DATABASE_URL=postgresql://user:pass@host:5432/tickerTap",
        file=sys.stderr,
    )
    sys.exit(1)

# Strip async driver prefix so synchronous Alembic connections work.
env_url = env_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", env_url)

# ── Logging ───────────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import model metadata here to enable --autogenerate support:
# from app.models import Base
# target_metadata = Base.metadata
target_metadata = None


# ── Migration runners ─────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required).

    Generates SQL statements instead of executing them directly.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
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
