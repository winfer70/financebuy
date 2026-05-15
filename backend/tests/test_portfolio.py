"""
============================================================================
TEST SUITE: Portfolio endpoints
============================================================================

MODULE UNDER TEST: app.routes.portfolio
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Tests GET /api/v1/portfolio/positions and
    GET /api/v1/portfolio/summary.
    Both endpoints require authentication and return portfolio data
    derived from the user's accounts and holdings.

COVERAGE SCOPE:
    ✓ GET /api/v1/portfolio/positions — no accounts returns []
    ✓ GET /api/v1/portfolio/positions — requires auth (401/403)
    ✓ GET /api/v1/portfolio/summary  — no accounts returns empty summary
    ✓ GET /api/v1/portfolio/summary  — requires auth (401/403)
============================================================================
"""

import os
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# Set env vars before any app import
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest

from tests.conftest import make_scalar_result, make_scalars_result, make_all_result


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: GET /api/v1/portfolio/positions
# ═══════════════════════════════════════════════════════════════════════════


class TestGetPositions:
    """Tests for the positions listing endpoint."""

    def test_no_accounts_returns_empty(self, auth_client):
        """User with no accounts should receive an empty positions list."""
        client, db, user = auth_client
        # First execute: account lookup returns empty list
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/portfolio/positions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_positions_require_auth(self):
        """GET /positions without auth should return 401 or 403."""
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        async def override_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/portfolio/positions")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /api/v1/portfolio/summary
# ═══════════════════════════════════════════════════════════════════════════


class TestPortfolioSummary:
    """Tests for the portfolio summary endpoint."""

    def test_summary_no_accounts(self, auth_client):
        """User with no accounts should receive a zero-value summary."""
        client, db, user = auth_client
        # First execute: account lookup returns empty list → early return path
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/portfolio/summary")
        assert resp.status_code == 200
        data = resp.json()
        # The summary should report zero total value and an empty account list
        assert data.get("accounts") == []
        assert float(data.get("total_portfolio_value", -1)) == 0.0

    def test_summary_requires_auth(self):
        """GET /summary without auth should return 401 or 403."""
        from app.main import app
        from app.db import get_db
        from fastapi.testclient import TestClient

        async def override_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/portfolio/summary")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
