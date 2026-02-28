"""
============================================================================
TEST SUITE: Orders — placement validation helpers
============================================================================

MODULE UNDER TEST: app.routes.orders
TEST TYPE: Unit (helper functions)
FRAMEWORK: pytest

DESCRIPTION:
    Tests the pure validation helpers (_normalize_side, _normalize_order_type)
    and the place_order business-rule checks (quantity > 0, price > 0) without
    requiring a live database. HTTP-level tests use the FastAPI TestClient with
    a fully mocked database session.

COVERAGE SCOPE:
    ✓ _normalize_side      — valid/invalid inputs
    ✓ _normalize_order_type — valid/invalid inputs
    ✓ POST /orders          — quantity validation
    ✓ POST /orders          — price validation
    ✓ POST /orders          — account-not-found (404)

EXECUTION REQUIREMENTS:
    - No external services required
    - Run: pytest backend/tests/test_orders.py -v
============================================================================
"""

import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# ── PYTHONPATH ──────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-for-validation")


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: _normalize_side helper
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeSide:
    """Unit tests for the _normalize_side validation helper."""

    def setup_method(self):
        from app.routes.orders import _normalize_side
        self.normalize = _normalize_side

    def test_buy_is_accepted(self):
        """'buy' (any case) should return 'buy'."""
        assert self.normalize("buy") == "buy"
        assert self.normalize("BUY") == "buy"
        assert self.normalize("Buy") == "buy"

    def test_sell_is_accepted(self):
        """'sell' (any case) should return 'sell'."""
        assert self.normalize("sell") == "sell"
        assert self.normalize("SELL") == "sell"

    def test_invalid_side_raises_400(self):
        """An invalid side value should raise HTTPException with status 400."""
        with pytest.raises(HTTPException) as exc_info:
            self.normalize("hold")
        assert exc_info.value.status_code == 400
        assert "buy" in exc_info.value.detail or "sell" in exc_info.value.detail

    def test_empty_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.normalize("")
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: _normalize_order_type helper
# ═══════════════════════════════════════════════════════════════════════════

class TestNormalizeOrderType:
    """Unit tests for the _normalize_order_type validation helper."""

    def setup_method(self):
        from app.routes.orders import _normalize_order_type
        self.normalize = _normalize_order_type

    def test_market_is_accepted(self):
        assert self.normalize("market") == "market"
        assert self.normalize("MARKET") == "market"

    def test_limit_is_accepted(self):
        assert self.normalize("limit") == "limit"
        assert self.normalize("LIMIT") == "limit"

    def test_invalid_type_raises_400(self):
        """An unrecognised order type should raise 400."""
        with pytest.raises(HTTPException) as exc_info:
            self.normalize("stop")
        assert exc_info.value.status_code == 400

    def test_empty_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            self.normalize("")
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: POST /orders — HTTP-level validation
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def auth_client():
    """
    TestClient with:
      - DB dependency returning a mock account with sufficient balance
      - get_current_user returning a mock authenticated user
    """
    from app.main import app
    from app.db import get_db
    from app.routes.auth_routes import get_current_user
    from app.models import Account, Security

    # Mock user
    mock_user = MagicMock()
    mock_user.user_id = uuid.uuid4()

    # Mock account with balance
    mock_account = MagicMock(spec=Account)
    mock_account.account_id = uuid.uuid4()
    mock_account.user_id    = mock_user.user_id
    mock_account.balance    = Decimal("50000.00")

    # Mock security
    mock_security = MagicMock(spec=Security)
    mock_security.security_id = uuid.uuid4()
    mock_security.symbol      = "AAPL"
    mock_security.is_active   = True

    async def override_db():
        session = AsyncMock()

        def execute_side_effect(stmt):
            mock_result = MagicMock()
            # First call → account lookup; subsequent → security lookup
            mock_result.scalar_one_or_none.return_value = mock_account
            return mock_result

        session.execute = AsyncMock(side_effect=execute_side_effect)
        session.add     = MagicMock()
        session.commit  = AsyncMock()
        session.refresh = AsyncMock()
        yield session

    async def override_auth():
        return mock_user

    app.dependency_overrides[get_db]           = override_db
    app.dependency_overrides[get_current_user] = override_auth

    yield TestClient(app), mock_account, mock_security, mock_user
    app.dependency_overrides.clear()


class TestPlaceOrderEndpoint:
    """HTTP integration tests for POST /orders."""

    def _base_payload(self, account_id, security_id):
        return {
            "account_id":  str(account_id),
            "security_id": str(security_id),
            "order_type":  "limit",
            "side":        "buy",
            "quantity":    "5",
            "price":       "150.00",
        }

    def test_returns_400_for_zero_quantity(self, auth_client):
        """quantity = 0 should return 400 Bad Request."""
        client, account, security, _ = auth_client
        payload = self._base_payload(account.account_id, security.security_id)
        payload["quantity"] = "0"

        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "quantity" in response.json().get("detail", "").lower()

    def test_returns_400_for_negative_quantity(self, auth_client):
        """quantity < 0 should return 400 Bad Request."""
        client, account, security, _ = auth_client
        payload = self._base_payload(account.account_id, security.security_id)
        payload["quantity"] = "-1"

        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_returns_400_for_zero_price(self, auth_client):
        """price = 0 should return 400 Bad Request."""
        client, account, security, _ = auth_client
        payload = self._base_payload(account.account_id, security.security_id)
        payload["price"] = "0"

        response = client.post("/orders", json=payload)
        assert response.status_code == 400
        assert "price" in response.json().get("detail", "").lower()

    def test_returns_400_for_invalid_side(self, auth_client):
        """Invalid side value should return 400."""
        client, account, security, _ = auth_client
        payload = self._base_payload(account.account_id, security.security_id)
        payload["side"] = "hold"

        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_returns_400_for_invalid_order_type(self, auth_client):
        """Invalid order_type should return 400."""
        client, account, security, _ = auth_client
        payload = self._base_payload(account.account_id, security.security_id)
        payload["order_type"] = "stop"

        response = client.post("/orders", json=payload)
        assert response.status_code == 400

    def test_returns_404_when_account_not_found(self, auth_client):
        """If the account does not belong to the current user, return 404."""
        from app.main import app
        from app.db import get_db

        async def override_no_account():
            session = AsyncMock()
            session.execute.return_value.scalar_one_or_none.return_value = None
            yield session

        client, account, security, _ = auth_client
        app.dependency_overrides[get_db] = override_no_account

        payload = self._base_payload(uuid.uuid4(), uuid.uuid4())
        response = client.post("/orders", json=payload)

        assert response.status_code == 404
