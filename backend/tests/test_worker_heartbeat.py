"""
TEST SUITE: Worker Heartbeat Cron
MODULE UNDER TEST: app.trading.worker
TEST TYPE: Unit

DESCRIPTION:
    Verifies that the trading worker has a cron job configured to keep the
    heartbeat key alive between jobs, and that _periodic_heartbeat delegates
    correctly to write_worker_heartbeat.

COVERAGE SCOPE:
    ✓ WorkerSettings.cron_jobs is non-empty (at least one cron entry present)
    ✓ _periodic_heartbeat calls write_worker_heartbeat with correct arguments:
        worker_name="trading-worker", jobs_processed_delta=0, last_error=""
"""

import os
from unittest.mock import AsyncMock, patch, call

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


def test_trading_worker_cron_jobs_configured():
    """WorkerSettings must declare at least one cron job for the heartbeat.

    Verifies that the cron_jobs list is non-empty so the periodic heartbeat
    is registered with arq at worker startup.
    """
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        from app.trading.worker import WorkerSettings

        assert hasattr(WorkerSettings, "cron_jobs"), (
            "WorkerSettings must have a cron_jobs attribute"
        )
        assert len(WorkerSettings.cron_jobs) > 0, (
            "WorkerSettings.cron_jobs must not be empty"
        )


@pytest.mark.asyncio
async def test_periodic_heartbeat_calls_write_worker_heartbeat():
    """_periodic_heartbeat must call write_worker_heartbeat with correct args.

    The heartbeat function should pass worker_name="trading-worker",
    jobs_processed_delta=0 (not incrementing the jobs counter), and
    an empty last_error string.
    """
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine"),
        patch("sqlalchemy.orm.sessionmaker"),
    ):
        import app.trading.worker as worker_mod

        mock_write_heartbeat = AsyncMock()
        # Patch write_worker_heartbeat in the worker module's namespace
        with patch.object(worker_mod, "write_worker_heartbeat", mock_write_heartbeat):
            ctx = {}  # arq provides a dict context; not used by this function
            await worker_mod._periodic_heartbeat(ctx)

    mock_write_heartbeat.assert_called_once_with(
        "trading-worker",
        worker_mod._REDIS_URL,
        jobs_processed_delta=0,
        last_error="",
    )
