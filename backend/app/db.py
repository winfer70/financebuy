"""
db.py — Async SQLAlchemy engine and session factory for TickerTap.

Provides a single shared engine (with connection pool limits) and the
`get_db` dependency used by all route handlers to obtain a session.

Pool configuration (P6.4):
  pool_size=20   — maximum persistent connections kept open
  max_overflow=10 — temporary connections allowed above pool_size
  pool_pre_ping=True — recycle stale connections before use (handles DB restarts)
  pool_recycle=3600  — recycle connections after 1 hour to avoid idle timeouts
"""

import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Database URL ──────────────────────────────────────────────────────────────
_DEFAULT_DB = "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT_DB)

# Refuse to run in production with default credentials — P6.4 / security guard
_env = os.getenv("ENVIRONMENT", "development").lower()
if _env == "production" and DATABASE_URL == _DEFAULT_DB:
    print(
        "FATAL: DATABASE_URL is still the insecure default in a production environment. "
        "Set a strong DATABASE_URL environment variable before starting.",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Engine — connection pool limits applied (P6.4) ────────────────────────────
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    # Connection pool settings
    pool_size=20,       # Persistent connections always kept open
    max_overflow=10,    # Extra connections allowed under burst load
    pool_pre_ping=True, # Test connections before use; recycle dead ones
    pool_recycle=3600,  # Recycle connections after 1 hour
)

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    """FastAPI dependency: yield an async database session per request.

    The session is automatically closed when the request completes,
    ensuring connections are returned to the pool promptly.

    Yields:
        AsyncSession: A live SQLAlchemy async session.
    """
    async with AsyncSessionLocal() as session:
        yield session
