"""
============================================================================
TEST SUITE: Trading strategy and backtest endpoints
============================================================================

MODULE UNDER TEST: app.routes.trading
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Tests GET /api/v1/trading/strategies, GET /api/v1/trading/strategies/{id},
    and POST /api/v1/trading/backtest.
    The arq worker's enqueue_backtest is patched to avoid Redis dependency.

COVERAGE SCOPE:
    ✓ GET  /api/v1/trading/strategies         — empty, populated, requires auth
    ✓ GET  /api/v1/trading/strategies/{id}    — success, 404, system strategy
    ✓ POST /api/v1/trading/backtest           — pending result (201)
    ✓ POST /api/v1/trading/backtest           — missing strategy returns 422
============================================================================
"""

import os
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

# Set env vars before any app import
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest

from tests.conftest import make_scalar_result, make_scalars_result


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_strategy(user_id, is_system=False):
    """Build a MagicMock that quacks like a Strategy ORM instance.

    Args:
        user_id:   UUID of the owning user (None for system strategies).
        is_system: True if this should be a platform-provided strategy.

    Returns:
        MagicMock with all StrategyOut fields populated.
    """
    s = MagicMock()
    s.strategy_id = uuid.uuid4()
    s.user_id = None if is_system else user_id
    s.name = "Test Strategy"
    s.description = "A test strategy"
    s.definition_json = {"strategy_slug": "sma_crossover"}
    s.is_public = False
    s.is_system = is_system
    s.version = 1
    s.strategy_type = "builtin"
    s.category = None
    s.timeframe = None
    s.asset_class = None
    s.created_at = datetime.utcnow()
    s.updated_at = datetime.utcnow()
    return s


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: GET /api/v1/trading/strategies
# ═══════════════════════════════════════════════════════════════════════════


class TestListStrategies:
    """Tests for the strategy listing endpoint."""

    def test_list_strategies_empty(self, auth_client):
        """User with no strategies should receive an empty JSON array."""
        client, db, user = auth_client
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/trading/strategies")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_strategies_returns_list(self, auth_client):
        """User with two strategies should receive a list of length 2."""
        client, db, user = auth_client
        s1 = make_mock_strategy(user.user_id)
        s2 = make_mock_strategy(user.user_id, is_system=True)
        db.execute.return_value = make_scalars_result([s1, s2])

        resp = client.get("/api/v1/trading/strategies")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_strategies_requires_auth(self):
        """GET /strategies without auth should return 401 or 403."""
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        async def override_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/trading/strategies")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /api/v1/trading/strategies/{id}
# ═══════════════════════════════════════════════════════════════════════════


class TestGetStrategy:
    """Tests for single-strategy retrieval."""

    def test_get_strategy_success(self, auth_client):
        """Fetching an owned strategy by ID should return 200."""
        client, db, user = auth_client
        s = make_mock_strategy(user.user_id)
        db.execute.return_value = make_scalar_result(s)

        resp = client.get(f"/api/v1/trading/strategies/{s.strategy_id}")
        assert resp.status_code == 200

    def test_get_strategy_404(self, auth_client):
        """Fetching a non-existent strategy should return 404."""
        client, db, user = auth_client
        db.execute.return_value = make_scalar_result(None)

        resp = client.get(f"/api/v1/trading/strategies/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_system_strategy(self, auth_client):
        """System strategies should be accessible to any authenticated user."""
        client, db, user = auth_client
        s = make_mock_strategy(user.user_id, is_system=True)
        db.execute.return_value = make_scalar_result(s)

        resp = client.get(f"/api/v1/trading/strategies/{s.strategy_id}")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: POST /api/v1/trading/backtest
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateBacktest:
    """Tests for the backtest queuing endpoint."""

    def test_create_backtest_returns_pending(self, auth_client):
        """Valid backtest request should create a pending result (201)."""
        client, db, user = auth_client
        strategy = make_mock_strategy(user.user_id)

        result_id = uuid.uuid4()

        # First execute: concurrent backtest count check (returns empty list)
        active_result = make_scalars_result([])
        # Second element is unused when strategy_id is provided (no slug lookup)
        db.execute.side_effect = [active_result, make_scalar_result(strategy)]

        async def refresh_side_effect(obj):
            # Simulate DB populating fields after INSERT + refresh
            obj.result_id = result_id
            obj.user_id = user.user_id
            obj.symbol = "AAPL"
            obj.interval = "1d"
            obj.status = "pending"
            obj.created_at = datetime.utcnow()
            obj.completed_at = None
            obj.results_json = None
            obj.metrics_json = None
            obj.benchmark_json = None
            obj.parameters_json = {}
            obj.error_message = None
            obj.strategy_id = strategy.strategy_id
            obj.overfit_warning = False
            obj.start_date = datetime(2023, 1, 1)
            obj.end_date = datetime(2024, 1, 1)

        db.refresh.side_effect = refresh_side_effect

        # Patch enqueue_backtest so no Redis connection is attempted.
        # Exceptions from enqueue are caught in the route, so this patch
        # is defensive rather than strictly required.
        with patch(
            "app.trading.worker.enqueue_backtest",
            new=AsyncMock(return_value="job-id"),
        ):
            resp = client.post(
                "/api/v1/trading/backtest",
                json={
                    "strategy_id": str(strategy.strategy_id),
                    "symbol": "AAPL",
                    "interval": "1d",
                    "start_date": "2023-01-01",
                    "end_date": "2024-01-01",
                },
            )

        assert resp.status_code in (200, 201)
        if resp.status_code in (200, 201):
            assert resp.json().get("status") == "pending"

    def test_create_backtest_missing_strategy_422(self, auth_client):
        """Omitting both strategy_id and strategy_slug must return 422.

        BacktestRequest has a @root_validator that raises ValueError when
        neither field is provided, which Pydantic translates to 422.
        """
        client, db, user = auth_client
        resp = client.post(
            "/api/v1/trading/backtest",
            json={
                "symbol": "AAPL",
                "interval": "1d",
                "start_date": "2023-01-01",
                "end_date": "2024-01-01",
                # strategy_id and strategy_slug both absent
            },
        )
        assert resp.status_code == 422
