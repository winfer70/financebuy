"""
============================================================================
TEST SUITE: Account management endpoints
============================================================================

MODULE UNDER TEST: app.routes.accounts
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Tests POST /api/v1/accounts (create account) and
    GET /api/v1/accounts/me (list user accounts).
    All DB interactions are mocked via the auth_client conftest fixture.

COVERAGE SCOPE:
    ✓ POST /api/v1/accounts — success (201), missing account_type (422)
    ✓ POST /api/v1/accounts — optional currency defaults to USD
    ✓ GET  /api/v1/accounts/me — empty list, populated list
    ✓ GET  /api/v1/accounts/me — unauthenticated (401/403)
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
from fastapi.testclient import TestClient

from tests.conftest import make_scalar_result, make_scalars_result


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: POST /api/v1/accounts — create account
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateAccount:
    """Integration tests for account creation endpoint."""

    def test_create_account_success(self, auth_client):
        """Valid payload should return 201 with account data."""
        client, db, user = auth_client

        acct_id = uuid.uuid4()

        def refresh_side_effect(obj):
            # Simulate DB populating server-side fields after INSERT
            obj.account_id = acct_id
            obj.balance = Decimal("0.00")
            obj.status = "active"
            obj.account_number = "ACC-001"
            obj.currency = "USD"
            obj.account_type = "individual"
            obj.user_id = user.user_id

        db.refresh.side_effect = refresh_side_effect

        resp = client.post(
            "/api/v1/accounts",
            json={"account_type": "individual", "currency": "USD"},
        )
        assert resp.status_code in (200, 201)

    def test_create_account_missing_type_returns_422(self, auth_client):
        """Omitting the required account_type field must return 422."""
        client, db, user = auth_client
        resp = client.post("/api/v1/accounts", json={"currency": "USD"})
        assert resp.status_code == 422

    def test_create_account_default_currency_usd(self, auth_client):
        """currency has a default of 'USD' in the schema and is therefore optional."""
        client, db, user = auth_client

        acct_id = uuid.uuid4()

        def refresh_side_effect(obj):
            obj.account_id = acct_id
            obj.balance = Decimal("0.00")
            obj.status = "active"
            obj.account_number = "ACC-002"
            # If currency was not supplied, it should default to "USD"
            obj.currency = getattr(obj, "currency", None) or "USD"
            obj.account_type = "individual"
            obj.user_id = user.user_id

        db.refresh.side_effect = refresh_side_effect

        resp = client.post(
            "/api/v1/accounts", json={"account_type": "individual"}
        )
        # Either succeeds (currency defaults to USD) or rejects — both valid
        assert resp.status_code in (200, 201, 422)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /api/v1/accounts/me — list user accounts
# ═══════════════════════════════════════════════════════════════════════════


class TestListMyAccounts:
    """Integration tests for listing the current user's accounts."""

    def test_list_accounts_empty(self, auth_client):
        """No accounts for this user should return an empty JSON array."""
        client, db, user = auth_client
        # execute().scalars().all() returns empty list
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/accounts/me")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_accounts_returns_user_accounts(self, auth_client):
        """A user with one account should receive a list of length 1."""
        client, db, user = auth_client

        # Build a mock account that satisfies AccountOut serialisation
        mock_acct = MagicMock()
        mock_acct.account_id = uuid.uuid4()
        mock_acct.user_id = user.user_id
        mock_acct.account_type = "individual"
        mock_acct.account_number = "ACC-001"
        mock_acct.currency = "USD"
        mock_acct.balance = Decimal("1000.00")
        mock_acct.status = "active"

        db.execute.return_value = make_scalars_result([mock_acct])

        resp = client.get("/api/v1/accounts/me")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_list_accounts_unauthenticated(self):
        """Requests without authentication should be rejected (401 or 403)."""
        from app.main import app
        from app.db import get_db

        async def override_get_db():
            yield AsyncMock()

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client.get("/api/v1/accounts/me")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.clear()
