"""
============================================================================
TEST SUITE: Orders — market orders price at the live quote, not the client price
============================================================================

MODULE UNDER TEST: app.routes.orders.place_order
TEST TYPE: Unit (direct coroutine invocation, DB + market data mocked)
FRAMEWORK: pytest + pytest-asyncio + unittest.mock

DESCRIPTION:
    Regression test for a money-correctness bug: place_order used
    payload.price directly as the fill price for market orders, so a client
    could submit e.g. price=0.01 on a market buy and receive shares far
    below actual value, or price=999999 on a market sell to extract cash
    with no offsetting real value — the API enforced nothing about the fill
    price for an order type whose entire definition is "filled at the
    current market price."

    place_order now resolves the security's symbol, fetches a live quote via
    app.routes.market.get_live_price, and uses that as the fill price for
    market orders regardless of what the client submitted. Limit orders are
    unaffected — a limit order's whole point is filling at the client's
    stated price when later executed.

    Calling the coroutine directly (not through the FastAPI HTTP layer) sidesteps
    OrderOut response_model serialization, which needs server-side column
    defaults (placed_at) that only populate on a real DB flush.

COVERAGE SCOPE:
    ✓ Market buy — fill price comes from the live quote, not payload.price
    ✓ Market sell — same
    ✓ Live quote fetch failure — 503, no account mutation
============================================================================
"""
import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "memory://")

import pytest
from fastapi import HTTPException

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.conftest import make_scalar_result


def _make_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    _cm = MagicMock()
    _cm.__aenter__ = AsyncMock(return_value=None)
    _cm.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=_cm)
    return session


def _make_account(balance):
    account = MagicMock()
    account.account_id = uuid.uuid4()
    account.balance = balance
    return account


class TestMarketOrderPricing:
    @pytest.mark.asyncio
    async def test_market_buy_fills_at_live_price_not_client_price(self):
        from app.routes import orders as orders_module
        from app.schemas import OrderCreate

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        account = _make_account(Decimal("100000.00"))
        security_id = uuid.uuid4()

        # Order of SELECTs in place_order's market path: security symbol,
        # then (locked account, no holding) inside the account transaction.
        db.execute.side_effect = [
            make_scalar_result("AAPL"),
            make_scalar_result(account),
            make_scalar_result(None),
        ]

        payload = OrderCreate(
            account_id=account.account_id,
            security_id=security_id,
            order_type="market",
            side="buy",
            quantity=Decimal("10"),
            price=Decimal("0.01"),  # attacker-supplied bogus price — must be ignored
        )

        with patch.object(orders_module, "get_live_price", AsyncMock(return_value=201.23)):
            order = await orders_module.place_order(payload, db, user)

        assert order.price == Decimal("201.23")
        assert order.filled_price == Decimal("201.23")
        assert account.balance == Decimal("100000.00") - (Decimal("10") * Decimal("201.23"))

    @pytest.mark.asyncio
    async def test_market_sell_fills_at_live_price_not_client_price(self):
        from app.routes import orders as orders_module
        from app.schemas import OrderCreate

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        account = _make_account(Decimal("0.00"))
        security_id = uuid.uuid4()
        holding = MagicMock()
        holding.quantity = Decimal("10")
        holding.average_cost = Decimal("150.00")

        db.execute.side_effect = [
            make_scalar_result("AAPL"),
            make_scalar_result(account),
            make_scalar_result(holding),
        ]

        payload = OrderCreate(
            account_id=account.account_id,
            security_id=security_id,
            order_type="market",
            side="sell",
            quantity=Decimal("10"),
            price=Decimal("999999.00"),  # attacker-supplied bogus price — must be ignored
        )

        with patch.object(orders_module, "get_live_price", AsyncMock(return_value=201.23)):
            order = await orders_module.place_order(payload, db, user)

        assert order.price == Decimal("201.23")
        assert account.balance == Decimal("10") * Decimal("201.23")

    @pytest.mark.asyncio
    async def test_live_quote_failure_returns_503_and_does_not_touch_account(self):
        from app.routes import orders as orders_module
        from app.schemas import OrderCreate

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        account_id = uuid.uuid4()
        security_id = uuid.uuid4()

        db.execute.side_effect = [make_scalar_result("AAPL")]

        payload = OrderCreate(
            account_id=account_id,
            security_id=security_id,
            order_type="market",
            side="buy",
            quantity=Decimal("10"),
            price=Decimal("150.00"),
        )

        with patch.object(
            orders_module, "get_live_price", AsyncMock(side_effect=RuntimeError("yfinance down"))
        ):
            with pytest.raises(HTTPException) as exc_info:
                await orders_module.place_order(payload, db, user)

        assert exc_info.value.status_code == 503
        # Only the symbol lookup happened — no account lock/mutation was attempted.
        assert db.execute.call_count == 1
