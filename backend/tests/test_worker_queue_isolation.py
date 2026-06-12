"""
TEST SUITE: Worker Queue Isolation
MODULE UNDER TEST: app.trading.worker, app.trading.paper_worker, app.trading.alert_worker, app.trading.scanner_worker
TEST TYPE: Unit

DESCRIPTION:
    Verifies that every arq worker declares its own dedicated queue name and
    that all enqueue_job calls target the correct queue via _queue_name.
    No live Redis or database connection is required — all external calls are
    mocked.

COVERAGE SCOPE:
    ✓ WorkerSettings.queue_name == "arq:trading"  (trading worker)
    ✓ WorkerSettings.queue_name == "arq:paper"    (paper worker)
    ✓ WorkerSettings.queue_name == "arq:alert"    (alert worker)
    ✓ enqueue_backtest passes _queue_name="arq:trading" to enqueue_job
    ✓ enqueue_scanner  passes _queue_name="arq:trading" to enqueue_job
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Set required env vars before any app import so module-level code succeeds
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap",
)

import pytest


# ---------------------------------------------------------------------------
# WorkerSettings.queue_name assertions
# ---------------------------------------------------------------------------


def test_trading_worker_queue_name():
    """WorkerSettings in trading worker must use the dedicated trading queue.

    Importing worker.py triggers DB/Redis engine creation at module level, so
    we patch both to avoid real network calls.
    """
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        from app.trading.worker import WorkerSettings

        assert WorkerSettings.queue_name == "arq:trading", (
            f"Expected 'arq:trading', got {WorkerSettings.queue_name!r}"
        )


def test_paper_worker_queue_name():
    """WorkerSettings in paper_worker must use the dedicated paper queue."""
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        from app.trading.paper_worker import WorkerSettings as PaperSettings

        assert PaperSettings.queue_name == "arq:paper", (
            f"Expected 'arq:paper', got {PaperSettings.queue_name!r}"
        )


def test_alert_worker_queue_name():
    """WorkerSettings in alert_worker must use the dedicated alert queue."""
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        from app.trading.alert_worker import WorkerSettings as AlertSettings

        assert AlertSettings.queue_name == "arq:alert", (
            f"Expected 'arq:alert', got {AlertSettings.queue_name!r}"
        )


# ---------------------------------------------------------------------------
# enqueue_backtest — _queue_name forwarded correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_backtest_uses_trading_queue():
    """enqueue_backtest must pass _queue_name='arq:trading' to enqueue_job.

    The module-level Redis pool is replaced with an AsyncMock so no real
    Redis connection is attempted.
    """
    mock_job = MagicMock()
    mock_job.job_id = "fake-job-id"

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
        patch("app.trading.worker._get_redis", return_value=mock_redis),
    ):
        # Re-import after patching to pick up mocked _get_redis
        import importlib
        import app.trading.worker as worker_mod

        worker_mod._redis_pool = mock_redis

        await worker_mod.enqueue_backtest("test-backtest-id-123")

    mock_redis.enqueue_job.assert_called_once_with(
        "run_backtest", "test-backtest-id-123", _queue_name="arq:trading"
    )


# ---------------------------------------------------------------------------
# enqueue_scanner — _queue_name forwarded correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_scanner_uses_trading_queue():
    """enqueue_scanner must pass _queue_name='arq:trading' to enqueue_job.

    The module-level Redis pool in scanner_worker is replaced with an
    AsyncMock so no real Redis connection is attempted.
    """
    mock_job = MagicMock()
    mock_job.job_id = "fake-scan-job-id"

    mock_redis = AsyncMock()
    mock_redis.enqueue_job = AsyncMock(return_value=mock_job)

    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        import app.trading.scanner_worker as scanner_mod

        scanner_mod._redis_pool = mock_redis

        result = await scanner_mod.enqueue_scanner("test-scan-result-id-456")

    assert result == "fake-scan-job-id"
    mock_redis.enqueue_job.assert_called_once_with(
        "run_scanner", "test-scan-result-id-456", _queue_name="arq:trading"
    )
