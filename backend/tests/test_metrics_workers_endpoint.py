"""
TEST SUITE: Worker Metrics Endpoint
MODULE UNDER TEST: app.routes.metrics
TEST TYPE: Unit

Tests the unauthenticated /api/v1/metrics/workers endpoint.
Redis is mocked via unittest.mock — no live Redis required.
"""
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# MUST set env vars before importing the app so no real Redis/DB connection
# is attempted during module load.
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test"
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app  # noqa: E402

client = TestClient(app)

_WORKERS = ["trading-worker", "paper-worker", "alert-worker"]

# ── Helper ────────────────────────────────────────────────────────────────────


def _make_redis_mock(get_return_value, hgetall_return_value=None):
    """Build a mock aioredis client with pre-configured async methods.

    Args:
        get_return_value:     Value returned by client.get() (string or None).
        hgetall_return_value: Dict returned by client.hgetall().  Defaults to
                              an empty dict when None is passed.

    Returns:
        MagicMock: Mock Redis client with get, hgetall, and aclose configured.
    """
    if hgetall_return_value is None:
        hgetall_return_value = {}
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=get_return_value)
    mock_client.hgetall = AsyncMock(return_value=hgetall_return_value)
    mock_client.aclose = AsyncMock(return_value=None)
    return mock_client


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_should_return_healthy_status_when_heartbeat_key_fresh():
    """All workers should report 'healthy' when their heartbeat is recent.

    A heartbeat age of 10 seconds is well within every worker's TTL threshold.
    """
    recent_ts = str(time.time() - 10)  # 10 seconds ago — comfortably healthy
    metrics_data = {
        "last_run": "2025-01-01T00:00:00+00:00",
        "last_error": "",
        "jobs_processed": "42",
    }
    mock_redis = _make_redis_mock(
        get_return_value=recent_ts,
        hgetall_return_value=metrics_data,
    )

    with patch(
        "app.routes.metrics.aioredis.Redis.from_url", return_value=mock_redis
    ):
        response = client.get("/api/v1/metrics/workers")

    assert response.status_code == 200
    body = response.json()
    for worker in _WORKERS:
        assert body[worker]["status"] == "healthy", (
            f"{worker} should be healthy but got {body[worker]['status']}"
        )
        assert body[worker]["age_seconds"] is not None
        assert body[worker]["jobs_processed"] == 42


def test_should_return_stale_status_when_heartbeat_age_exceeds_threshold():
    """All workers should report 'stale' when their heartbeat is 2000 s old.

    2000 seconds exceeds the TTL threshold of every worker (max is
    trading-worker at 1800 s), so all must be stale.
    """
    stale_ts = str(time.time() - 2000)  # 2000 s old — exceeds all thresholds
    mock_redis = _make_redis_mock(
        get_return_value=stale_ts,
        hgetall_return_value={"jobs_processed": "5", "last_error": "", "last_run": ""},
    )

    with patch(
        "app.routes.metrics.aioredis.Redis.from_url", return_value=mock_redis
    ):
        response = client.get("/api/v1/metrics/workers")

    assert response.status_code == 200
    body = response.json()
    for worker in _WORKERS:
        assert body[worker]["status"] == "stale", (
            f"{worker} should be stale but got {body[worker]['status']}"
        )
        assert body[worker]["age_seconds"] > 1800


def test_should_return_no_heartbeat_when_key_missing():
    """Workers should report 'no_heartbeat' when the Redis key does not exist.

    Redis returns None for keys that have expired or were never written.
    """
    mock_redis = _make_redis_mock(
        get_return_value=None,   # key absent — expired or never written
        hgetall_return_value={}, # metrics hash may also be empty
    )

    with patch(
        "app.routes.metrics.aioredis.Redis.from_url", return_value=mock_redis
    ):
        response = client.get("/api/v1/metrics/workers")

    assert response.status_code == 200
    body = response.json()
    for worker in _WORKERS:
        assert body[worker]["status"] == "no_heartbeat", (
            f"{worker} should be no_heartbeat but got {body[worker]['status']}"
        )
        assert body[worker]["age_seconds"] is None
        assert body[worker]["jobs_processed"] == 0


def test_should_return_error_dict_when_redis_unreachable():
    """Endpoint should return {error: ...} gracefully when Redis is down.

    aioredis.Redis.from_url raises ConnectionError to simulate a down Redis.
    The endpoint must not raise an exception — it should return an error dict.
    """
    with patch(
        "app.routes.metrics.aioredis.Redis.from_url",
        side_effect=ConnectionError("Connection refused"),
    ):
        response = client.get("/api/v1/metrics/workers")

    assert response.status_code == 200
    body = response.json()
    assert "error" in body, "Response must contain an 'error' key when Redis is down"
    assert "Connection refused" in body["error"]


def test_should_return_all_three_workers_in_response():
    """Response must contain exactly the three known arq workers as top-level keys."""
    recent_ts = str(time.time() - 5)
    mock_redis = _make_redis_mock(
        get_return_value=recent_ts,
        hgetall_return_value={"jobs_processed": "1"},
    )

    with patch(
        "app.routes.metrics.aioredis.Redis.from_url", return_value=mock_redis
    ):
        response = client.get("/api/v1/metrics/workers")

    assert response.status_code == 200
    body = response.json()
    expected_workers = {"trading-worker", "paper-worker", "alert-worker"}
    assert set(body.keys()) == expected_workers, (
        f"Expected workers {expected_workers} but got {set(body.keys())}"
    )
