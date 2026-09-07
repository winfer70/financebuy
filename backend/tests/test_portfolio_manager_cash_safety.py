"""
============================================================================
TEST SUITE: Portfolio Manager — cash-mutating endpoints
============================================================================

MODULE UNDER TEST: app.routes.portfolio_manager
TEST TYPE: Unit (direct coroutine invocation, DB mocked)
FRAMEWORK: pytest + pytest-asyncio + unittest.mock

DESCRIPTION:
    Regression tests for two money-correctness bugs fixed in this module:
      1. Cash-balance arithmetic was done in float instead of Decimal,
         letting binary floating-point rounding drift into stored balances.
      2. Portfolio/position rows were read-modify-written with no row lock,
         so two concurrent requests on the same portfolio could clobber
         each other's update (lost-update race).

    Tests call the route coroutines directly rather than through the FastAPI
    HTTP layer: add_position/sell_position build real ORM objects whose
    server-side column defaults (position_id, is_excluded, created_at) are
    only populated on a real DB flush, so response_model serialization needs
    a live database and is out of scope here. Calling the coroutines directly
    still exercises the exact arithmetic and locking behavior under test.

COVERAGE SCOPE:
    ✓ adjust_cash    — exact Decimal result; insufficient-funds still 400; locked
    ✓ add_position   — exact Decimal cost deduction; insufficient-cash still 400; locked
    ✓ sell_position  — exact Decimal proceeds credit (full sell); locked
============================================================================
"""
import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

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
    """Fresh mock AsyncSession — mirrors conftest's mock_db_session fixture
    for tests that call route coroutines directly instead of via auth_client."""
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


def _make_portfolio(cash_balance):
    portfolio = MagicMock()
    portfolio.portfolio_id = uuid.uuid4()
    portfolio.cash_balance = cash_balance
    return portfolio


def _make_position(portfolio_id, quantity, purchase_price):
    position = MagicMock()
    position.position_id = uuid.uuid4()
    position.portfolio_id = portfolio_id
    position.ticker = "AAPL"
    position.quantity = quantity
    position.purchase_price = purchase_price
    return position


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 1: POST /{portfolio_id}/cash
# ═══════════════════════════════════════════════════════════════════════════


class TestAdjustCash:
    @pytest.mark.asyncio
    async def test_exact_decimal_arithmetic_no_float_drift(self):
        from app.routes.portfolio_manager import adjust_cash
        from app.schemas import CashAdjustmentRequest

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("100.10"))
        db.execute.return_value = make_scalar_result(portfolio)

        result = await adjust_cash(
            portfolio.portfolio_id,
            CashAdjustmentRequest(amount=Decimal("0.20")),
            db,
            user,
        )

        # 100.10 + 0.20 must land exactly on 100.30 — the textbook case
        # (0.1 + 0.2 != 0.3) that float arithmetic gets wrong.
        assert portfolio.cash_balance == Decimal("100.30")
        assert result == {"cash_balance": 100.30}
        assert db.begin.called, "adjust_cash must lock the portfolio row via db.begin()"

    @pytest.mark.asyncio
    async def test_insufficient_funds_raises_400_and_does_not_mutate(self):
        from app.routes.portfolio_manager import adjust_cash
        from app.schemas import CashAdjustmentRequest

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("10.00"))
        db.execute.return_value = make_scalar_result(portfolio)

        with pytest.raises(HTTPException) as exc_info:
            await adjust_cash(
                portfolio.portfolio_id,
                CashAdjustmentRequest(amount=Decimal("-20.00")),
                db,
                user,
            )
        assert exc_info.value.status_code == 400
        assert portfolio.cash_balance == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 2: POST /portfolios/{portfolio_id}/positions
# ═══════════════════════════════════════════════════════════════════════════


class TestAddPosition:
    @pytest.mark.asyncio
    async def test_deduct_cash_exact_decimal(self):
        from app.routes.portfolio_manager import add_position
        from app.schemas import PositionCreate

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("1000.00"))
        db.execute.return_value = make_scalar_result(portfolio)

        payload = PositionCreate(
            ticker="AAPL",
            quantity=Decimal("3"),
            purchase_price=Decimal("19.99"),
            deduct_cash=True,
        )

        await add_position(portfolio.portfolio_id, payload, db, user)

        # 1000.00 - (3 * 19.99) = 940.03 exactly.
        assert portfolio.cash_balance == Decimal("940.03")
        assert db.begin.called, "add_position must lock the portfolio row via db.begin()"

    @pytest.mark.asyncio
    async def test_insufficient_cash_raises_400_and_does_not_mutate(self):
        from app.routes.portfolio_manager import add_position
        from app.schemas import PositionCreate

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("10.00"))
        db.execute.return_value = make_scalar_result(portfolio)

        payload = PositionCreate(
            ticker="AAPL",
            quantity=Decimal("1"),
            purchase_price=Decimal("19.99"),
            deduct_cash=True,
        )

        with pytest.raises(HTTPException) as exc_info:
            await add_position(portfolio.portfolio_id, payload, db, user)
        assert exc_info.value.status_code == 400
        assert portfolio.cash_balance == Decimal("10.00")


# ═══════════════════════════════════════════════════════════════════════════
# SUITE 3: POST /positions/{position_id}/sell
# ═══════════════════════════════════════════════════════════════════════════


class TestSellPosition:
    @pytest.mark.asyncio
    async def test_full_sell_credit_cash_exact_decimal(self):
        from app.routes.portfolio_manager import sell_position
        from app.schemas import SellRequest

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("500.00"))
        position = _make_position(portfolio.portfolio_id, Decimal("3"), Decimal("19.99"))

        # sell_position issues three SELECTs in order for a full sell:
        # locked position, locked portfolio, linked open TradeAnalysis (none here).
        db.execute.side_effect = [
            make_scalar_result(position),
            make_scalar_result(portfolio),
            make_scalar_result(None),
        ]

        result = await sell_position(
            position.position_id,
            SellRequest(quantity=Decimal("3"), credit_cash=True, sell_price=Decimal("21.50")),
            db,
            user,
        )

        # 500.00 + (3 * 21.50) = 564.50 exactly.
        assert portfolio.cash_balance == Decimal("564.50")
        assert result is None  # fully sold — position deleted, no body
        assert db.delete.called
        assert db.begin.called, "sell_position must lock the position/portfolio rows via db.begin()"

    @pytest.mark.asyncio
    async def test_partial_sell_credit_cash_exact_decimal(self):
        from app.routes.portfolio_manager import sell_position
        from app.schemas import SellRequest

        db = _make_db()
        user = MagicMock(user_id=uuid.uuid4())
        portfolio = _make_portfolio(Decimal("500.00"))
        position = _make_position(portfolio.portfolio_id, Decimal("3"), Decimal("19.99"))

        # Partial sell only issues two SELECTs: locked position, locked portfolio.
        db.execute.side_effect = [
            make_scalar_result(position),
            make_scalar_result(portfolio),
        ]

        result = await sell_position(
            position.position_id,
            SellRequest(quantity=Decimal("1"), credit_cash=True, sell_price=Decimal("21.50")),
            db,
            user,
        )

        # 500.00 + (1 * 21.50) = 521.50 exactly; remaining quantity 3 - 1 = 2.
        assert portfolio.cash_balance == Decimal("521.50")
        assert position.quantity == Decimal("2")
        assert result is position
        assert not db.delete.called
        assert db.begin.called, "sell_position must lock the position/portfolio rows via db.begin()"
