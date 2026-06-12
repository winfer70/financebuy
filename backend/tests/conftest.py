"""
============================================================================
Shared test fixtures for TickerTap backend tests.

Provides pytest fixtures and mock helper functions used across all test
modules.  Environment variables are set here BEFORE any app import to
prevent real Redis/DB connections during tests.
============================================================================
"""
import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# MUST set before any app imports to prevent Redis connection and
# JWT validation failure during module load.
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test"
)

import pytest
from fastapi.testclient import TestClient

# Ensure the backend/ directory is importable as the root package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Clear in-memory rate limit counters before every test.

    Prevents rate-limit state from bleeding between tests when the same
    app instance is reused across a pytest session.
    """
    from app.limiter import limiter
    storage = getattr(limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_user():
    """Mock authenticated user ORM object.

    Returns:
        MagicMock: User-like object with user_id, email, is_active, is_admin.
    """
    user = MagicMock()
    user.user_id = uuid.uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def mock_db_session():
    """Mock async DB session compatible with SQLAlchemy 1.4 AsyncSession.

    All methods that are awaited in routes are AsyncMock; synchronous
    methods (add) remain MagicMock.

    Returns:
        AsyncMock: Session with add, delete, commit, refresh, rollback,
            execute all pre-configured.
    """
    session = AsyncMock()
    # db.add() is synchronous in SQLAlchemy 1.4 — do NOT use AsyncMock
    session.add = MagicMock()
    # db.delete() is async in SQLAlchemy 1.4 (uses greenlet_spawn)
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    # db.begin() used as async context manager in route handlers
    _cm = MagicMock()
    _cm.__aenter__ = AsyncMock(return_value=None)
    _cm.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=_cm)
    return session


@pytest.fixture
def auth_client(mock_user, mock_db_session):
    """Factory: TestClient with auth and DB dependencies overridden.

    Yields a 3-tuple (client, mock_db_session, mock_user) so individual
    tests can configure execute return values before making requests.

    Args:
        mock_user:       Pre-built mock user fixture.
        mock_db_session: Pre-built mock DB session fixture.

    Yields:
        tuple[TestClient, AsyncMock, MagicMock]: (client, db, user)
    """
    from app.main import app
    from app.db import get_db
    from app.routes.auth_routes import get_current_user

    async def override_get_db():
        # Yields the pre-configured mock session
        yield mock_db_session

    async def override_get_current_user():
        # Returns the mock user unconditionally (no token validation)
        return mock_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # raise_server_exceptions=False lets us inspect 5xx status codes
    # rather than having the test framework re-raise the exception.
    client = TestClient(app, raise_server_exceptions=False)
    yield client, mock_db_session, mock_user

    # Clean up overrides so they don't bleed into other test modules
    app.dependency_overrides.clear()


# ── Mock result helpers ───────────────────────────────────────────────────────


def make_scalar_result(value):
    """Mock for single-row query: session.execute().scalar_one_or_none()

    Args:
        value: The value to return from scalar_one_or_none() / scalar_one().

    Returns:
        MagicMock with scalar_one_or_none and scalar_one pre-configured.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalar_one.return_value = value
    return result


def make_scalars_result(items):
    """Mock for multi-row query: session.execute().scalars().all()

    Args:
        items: List of items to return from scalars().all().

    Returns:
        MagicMock with scalars().all() and scalars().first() configured.
    """
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    scalars_mock.first.return_value = items[0] if items else None
    result.scalars.return_value = scalars_mock
    return result


def make_all_result(rows):
    """Mock for query returning tuples: session.execute().all()

    Args:
        rows: List of row tuples (e.g. [(WatchlistORM, item_count), ...]).

    Returns:
        MagicMock with all() pre-configured.
    """
    result = MagicMock()
    result.all.return_value = rows
    return result


def make_scalar_count_result(n):
    """Mock for count query: session.execute().scalar()

    Args:
        n: Integer count to return from scalar().

    Returns:
        MagicMock with scalar() and scalar_one_or_none() pre-configured.
    """
    result = MagicMock()
    result.scalar.return_value = n
    result.scalar_one_or_none.return_value = n
    return result
