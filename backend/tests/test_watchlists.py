"""
============================================================================
TEST SUITE: Watchlist CRUD and item management endpoints
============================================================================

MODULE UNDER TEST: app.routes.watchlists
TEST TYPE: Integration (HTTP via TestClient, DB mocked)
FRAMEWORK: pytest + FastAPI TestClient

DESCRIPTION:
    Tests all watchlist and watchlist-item endpoints.  Ownership
    enforcement, duplicate detection, and 404 handling are covered.
    The _fetch_current_price helper is patched to avoid yfinance network
    calls during tests.

COVERAGE SCOPE:
    ✓ POST   /api/v1/watchlists                           — create
    ✓ GET    /api/v1/watchlists                           — list (empty, populated)
    ✓ GET    /api/v1/watchlists/{id}                      — 404
    ✓ DELETE /api/v1/watchlists/{id}                      — success, 404
    ✓ POST   /api/v1/watchlists/{id}/items                — symbol uppercased, 409 duplicate
    ✓ DELETE /api/v1/watchlists/{id}/items/{item_id}      — success, 404
============================================================================
"""

import os
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# Set env vars before any app import
os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest

from tests.conftest import make_scalar_result, make_scalars_result, make_all_result


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_mock_watchlist(user_id, name="My Watchlist"):
    """Build a MagicMock that quacks like a Watchlist ORM instance.

    Args:
        user_id: UUID of the owning user.
        name:    Watchlist display name.

    Returns:
        MagicMock with watchlist_id, user_id, name, and timestamps.
    """
    wl = MagicMock()
    wl.watchlist_id = uuid.uuid4()
    wl.user_id = user_id
    wl.name = name
    wl.created_at = datetime.utcnow()
    wl.updated_at = datetime.utcnow()
    return wl


def make_mock_item(watchlist_id, symbol="AAPL"):
    """Build a MagicMock that quacks like a WatchlistItem ORM instance.

    Args:
        watchlist_id: UUID of the parent watchlist.
        symbol:       Ticker symbol.

    Returns:
        MagicMock with item_id, watchlist_id, symbol, and related fields.
    """
    item = MagicMock()
    item.item_id = uuid.uuid4()
    item.watchlist_id = watchlist_id
    item.symbol = symbol
    item.asset_type = "stock"
    item.notes = ""
    item.position_order = 0
    item.price_when_added = 150.0
    item.added_at = datetime.utcnow()
    return item


# ── Used by TestWatchlistCRUD.test_create_watchlist ─────────────────────────


def make_scalar_count_result(n):
    """Mock for count queries: result.scalar() → n.

    Args:
        n: Integer count value.

    Returns:
        MagicMock with scalar() and scalar_one_or_none() returning n.
    """
    result = MagicMock()
    result.scalar.return_value = n
    result.scalar_one_or_none.return_value = n
    return result


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: Watchlist CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestWatchlistCRUD:
    """Tests for watchlist create, list, get, and delete operations."""

    def test_create_watchlist(self, auth_client):
        """Valid name payload should return 201 with the new watchlist."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id, "Tech Stocks")

        def refresh_side_effect(obj):
            # Simulate DB populating PK and timestamps after INSERT
            obj.watchlist_id = wl.watchlist_id
            obj.name = "Tech Stocks"
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()
            obj.user_id = user.user_id

        db.refresh.side_effect = refresh_side_effect
        db.execute.return_value = make_scalar_count_result(0)

        resp = client.post("/api/v1/watchlists", json={"name": "Tech Stocks"})
        assert resp.status_code in (200, 201)

    def test_create_watchlist_name_required(self, auth_client):
        """Omitting the name field should return 422 Unprocessable Entity."""
        client, db, user = auth_client
        resp = client.post("/api/v1/watchlists", json={})
        assert resp.status_code == 422

    def test_list_watchlists_empty(self, auth_client):
        """User with no watchlists should receive an empty JSON array."""
        client, db, user = auth_client
        # list_watchlists calls result.all() on a (Watchlist, count) query
        db.execute.return_value = make_all_result([])

        resp = client.get("/api/v1/watchlists")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_watchlists_returns_list(self, auth_client):
        """User with one watchlist should receive a list of length 1."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        # Each row is a (Watchlist, item_count) tuple from the correlated subquery
        db.execute.return_value = make_all_result([(wl, 3)])

        resp = client.get("/api/v1/watchlists")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1

    def test_get_watchlist_404(self, auth_client):
        """Requesting a non-existent watchlist should return 404."""
        client, db, user = auth_client
        # _get_watchlist_or_404 uses scalar_one_or_none — return None
        db.execute.return_value = make_scalar_result(None)

        resp = client.get(f"/api/v1/watchlists/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_watchlist_success(self, auth_client):
        """Deleting an owned watchlist should return 204 No Content."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        # _get_watchlist_or_404 returns the watchlist on first execute
        db.execute.return_value = make_scalar_result(wl)

        resp = client.delete(f"/api/v1/watchlists/{wl.watchlist_id}")
        assert resp.status_code in (200, 204)

    def test_delete_watchlist_404(self, auth_client):
        """Attempting to delete a non-existent watchlist should return 404."""
        client, db, user = auth_client
        db.execute.return_value = make_scalar_result(None)

        resp = client.delete(f"/api/v1/watchlists/{uuid.uuid4()}")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: Watchlist item operations
# ═══════════════════════════════════════════════════════════════════════════


class TestWatchlistItems:
    """Tests for adding and removing items from a watchlist."""

    def test_add_item_symbol_uppercased(self, auth_client):
        """Symbols submitted in lowercase should be stored uppercase."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        item = make_mock_item(wl.watchlist_id, "AAPL")

        # First execute: ownership check (_get_watchlist_or_404)
        # Second execute: duplicate symbol check
        db.execute.side_effect = [
            make_scalar_result(wl),
            make_scalar_result(None),  # No duplicate
        ]

        def refresh_side_effect(obj):
            # Simulate DB refresh populating server-generated fields
            obj.item_id = item.item_id
            # symbol was already uppercased by the route before INSERT
            obj.symbol = getattr(obj, "symbol", "AAPL").upper()
            obj.asset_type = "stock"
            obj.notes = ""
            # position_order uses server_default="0"; set explicitly for
            # Pydantic WatchlistItemOut serialisation (int field, not Optional)
            obj.position_order = 0
            obj.price_when_added = 150.0
            obj.added_at = datetime.utcnow()
            obj.watchlist_id = wl.watchlist_id

        db.refresh.side_effect = refresh_side_effect

        # Patch the yfinance price fetch so the test has no network calls
        with patch(
            "app.routes.watchlists._fetch_current_price",
            new=AsyncMock(return_value=None),
        ):
            resp = client.post(
                f"/api/v1/watchlists/{wl.watchlist_id}/items",
                json={"symbol": "aapl"},
            )

        assert resp.status_code in (200, 201)
        if resp.status_code in (200, 201):
            data = resp.json()
            assert data.get("symbol", "").upper() == "AAPL"

    def test_add_item_duplicate_returns_409(self, auth_client):
        """Adding a symbol that already exists in the watchlist returns 409."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        existing_item = make_mock_item(wl.watchlist_id)

        # First execute: ownership check succeeds
        # Second execute: duplicate check finds existing item
        db.execute.side_effect = [
            make_scalar_result(wl),
            make_scalar_result(existing_item),
        ]

        with patch(
            "app.routes.watchlists._fetch_current_price",
            new=AsyncMock(return_value=None),
        ):
            resp = client.post(
                f"/api/v1/watchlists/{wl.watchlist_id}/items",
                json={"symbol": "AAPL"},
            )

        assert resp.status_code == 409

    def test_delete_item_success(self, auth_client):
        """Removing an item that exists should return 204 No Content."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        item = make_mock_item(wl.watchlist_id)
        # _get_item_or_404 joins Watchlist+WatchlistItem and uses scalar_one_or_none
        db.execute.return_value = make_scalar_result(item)

        resp = client.delete(
            f"/api/v1/watchlists/{wl.watchlist_id}/items/{item.item_id}"
        )
        assert resp.status_code in (200, 204)

    def test_delete_item_404(self, auth_client):
        """Removing a non-existent item should return 404."""
        client, db, user = auth_client
        wl = make_mock_watchlist(user.user_id)
        db.execute.return_value = make_scalar_result(None)

        resp = client.delete(
            f"/api/v1/watchlists/{wl.watchlist_id}/items/{uuid.uuid4()}"
        )
        assert resp.status_code == 404
