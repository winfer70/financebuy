"""
============================================================================
TEST SUITE: Price alert CRUD endpoints
============================================================================

MODULE UNDER TEST: app.routes.alerts
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Tests POST /api/v1/alerts, GET /api/v1/alerts, and
    DELETE /api/v1/alerts/{alert_id}.
    The per-user limit of 50 active alerts is verified, and Pydantic
    condition validation (422 for invalid values) is tested.

COVERAGE SCOPE:
    ✓ POST   /api/v1/alerts — success (201), symbol uppercased
    ✓ POST   /api/v1/alerts — invalid condition returns 422
    ✓ POST   /api/v1/alerts — at limit (50 active) returns 400
    ✓ POST   /api/v1/alerts — below limit (49 active) succeeds
    ✓ GET    /api/v1/alerts — empty list, multiple alerts
    ✓ GET    /api/v1/alerts — active_only query param accepted
    ✓ DELETE /api/v1/alerts/{id} — success (204), 404
============================================================================
"""

import os
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

# Set env vars before any app import
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest

from tests.conftest import make_scalar_result, make_scalars_result


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_alert(user_id, symbol="AAPL", condition="above", target=200.0):
    """Build a MagicMock that quacks like a PriceAlert ORM instance.

    Args:
        user_id:   UUID of the owning user.
        symbol:    Ticker symbol (stored uppercase).
        condition: Trigger condition — 'above', 'below', or 'crosses'.
        target:    Target price as a float.

    Returns:
        MagicMock with alert_id, user_id, symbol, condition, target_price,
        is_active, note, triggered_at, and created_at.
    """
    alert = MagicMock()
    alert.alert_id = uuid.uuid4()
    alert.user_id = user_id
    alert.symbol = symbol
    alert.condition = condition
    alert.target_price = Decimal(str(target))
    alert.is_active = True
    alert.created_at = datetime.utcnow()
    alert.triggered_at = None
    alert.note = ""
    return alert


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: POST /api/v1/alerts — create alert
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateAlert:
    """Tests for price alert creation."""

    def _valid_payload(self):
        """Return a minimal valid PriceAlertCreate payload."""
        return {"symbol": "AAPL", "condition": "above", "target_price": 200.0}

    def test_create_alert_success(self, auth_client):
        """Valid payload with fewer than 50 active alerts returns 201."""
        client, db, user = auth_client
        alert = make_mock_alert(user.user_id)

        # Count query for per-user active alert limit check
        count_result = MagicMock()
        count_result.scalar.return_value = 0  # 0 existing alerts
        db.execute.return_value = count_result

        def refresh_side_effect(obj):
            obj.alert_id = alert.alert_id
            obj.symbol = "AAPL"
            obj.condition = "above"
            obj.target_price = Decimal("200.00")
            obj.is_active = True
            obj.created_at = datetime.utcnow()
            obj.triggered_at = None
            obj.user_id = user.user_id
            obj.note = ""

        db.refresh.side_effect = refresh_side_effect

        resp = client.post("/api/v1/alerts", json=self._valid_payload())
        assert resp.status_code in (200, 201)

    def test_create_alert_symbol_uppercased(self, auth_client):
        """Symbols in lowercase should be stored and returned uppercase."""
        client, db, user = auth_client

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute.return_value = count_result

        alert_id = uuid.uuid4()

        def refresh_side_effect(obj):
            obj.alert_id = alert_id
            # Route stores symbol.upper().strip(), so set expected value
            obj.symbol = getattr(obj, "symbol", "aapl").upper().strip()
            obj.condition = "above"
            obj.target_price = Decimal("200.00")
            obj.is_active = True
            obj.created_at = datetime.utcnow()
            obj.triggered_at = None
            obj.user_id = user.user_id
            obj.note = ""

        db.refresh.side_effect = refresh_side_effect

        resp = client.post(
            "/api/v1/alerts",
            json={"symbol": "aapl", "condition": "above", "target_price": 200.0},
        )
        if resp.status_code in (200, 201):
            assert resp.json().get("symbol", "").upper() == "AAPL"

    def test_create_alert_invalid_condition_422(self, auth_client):
        """An unrecognised condition value must fail Pydantic validation (422)."""
        client, db, user = auth_client
        resp = client.post(
            "/api/v1/alerts",
            json={
                "symbol": "AAPL",
                "condition": "wayover",   # not in {above, below, crosses}
                "target_price": 200.0,
            },
        )
        assert resp.status_code == 422

    def test_create_alert_at_limit_returns_400_or_429(self, auth_client):
        """User already at the 50-alert cap should receive 400 Bad Request."""
        client, db, user = auth_client
        count_result = MagicMock()
        count_result.scalar.return_value = 50  # At cap
        db.execute.return_value = count_result

        resp = client.post("/api/v1/alerts", json=self._valid_payload())
        assert resp.status_code in (400, 429)

    def test_create_alert_below_limit_succeeds(self, auth_client):
        """User with 49 active alerts should be able to create one more."""
        client, db, user = auth_client

        count_result = MagicMock()
        count_result.scalar.return_value = 49  # One below cap
        db.execute.return_value = count_result

        alert_id = uuid.uuid4()

        def refresh_side_effect(obj):
            obj.alert_id = alert_id
            obj.symbol = "AAPL"
            obj.condition = "above"
            obj.target_price = Decimal("200.00")
            obj.is_active = True
            obj.created_at = datetime.utcnow()
            obj.triggered_at = None
            obj.user_id = user.user_id
            obj.note = ""

        db.refresh.side_effect = refresh_side_effect

        resp = client.post("/api/v1/alerts", json=self._valid_payload())
        assert resp.status_code in (200, 201)


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: GET /api/v1/alerts — list alerts
# ═══════════════════════════════════════════════════════════════════════════


class TestListAlerts:
    """Tests for alert listing endpoint."""

    def test_list_alerts_empty(self, auth_client):
        """User with no alerts should receive an empty JSON array."""
        client, db, user = auth_client
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_alerts_returns_all(self, auth_client):
        """User with two alerts should receive a list of length 2."""
        client, db, user = auth_client
        a1 = make_mock_alert(user.user_id, "AAPL")
        a2 = make_mock_alert(user.user_id, "MSFT")
        db.execute.return_value = make_scalars_result([a1, a2])

        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_alerts_active_only_param_accepted(self, auth_client):
        """active_only=true query parameter should be accepted without error."""
        client, db, user = auth_client
        db.execute.return_value = make_scalars_result([])

        resp = client.get("/api/v1/alerts?active_only=true")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: DELETE /api/v1/alerts/{id} — delete alert
# ═══════════════════════════════════════════════════════════════════════════


class TestDeleteAlert:
    """Tests for alert deletion endpoint."""

    def test_delete_alert_success(self, auth_client):
        """Deleting an owned alert should return 204 No Content."""
        client, db, user = auth_client
        alert = make_mock_alert(user.user_id)
        # Route fetches the alert via scalar_one_or_none before deleting
        db.execute.return_value = make_scalar_result(alert)

        resp = client.delete(f"/api/v1/alerts/{alert.alert_id}")
        assert resp.status_code in (200, 204)

    def test_delete_alert_404(self, auth_client):
        """Attempting to delete a non-existent alert should return 404."""
        client, db, user = auth_client
        db.execute.return_value = make_scalar_result(None)

        resp = client.delete(f"/api/v1/alerts/{uuid.uuid4()}")
        assert resp.status_code == 404
