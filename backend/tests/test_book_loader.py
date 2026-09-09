"""
============================================================================
TEST SUITE: book_loader.load_books (portfolio + watchlist parity)
============================================================================

Covers the extraction of load_books()/load_avoid_tickers() out of
insider_monitor.py (needed so form144_monitor.py can share it without a
circular import) and the new watchlist join: a user with ONLY watchlist
items (no portfolio position) must still get a BookSnapshot — before this
change such a user never appeared in the books dict at all, since it was
built exclusively from portfolio-position rows.
============================================================================
"""
import os
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.trading.book_loader import load_books


def _mock_position(**overrides):
    pos = MagicMock()
    defaults = dict(
        ticker="AAPL",
        sector="Technology",
        t2_usd=None,
        purchase_price=Decimal("150.00"),
        quantity=Decimal("10"),
        hard_stop_loss=Decimal("140.00"),
        soft_stop_loss=Decimal("145.00"),
        date_entered=date(2026, 8, 1),
    )
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(pos, k, v)
    return pos


def _positions_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _watchlist_result(rows: list) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


class TestLoadBooksWatchlistParity:
    @pytest.mark.asyncio
    async def test_watchlist_only_user_still_gets_a_book(self):
        """The key regression this test guards: before the watchlist join,
        a user with zero portfolio positions never appeared in the books
        dict at all — load_books() was built exclusively from position rows."""
        uid = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([]),
                _watchlist_result([("MSFT", uid)]),
            ]
        )

        books, sectors = await load_books(session)

        assert uid in books
        assert books[uid].held_tickers == set()
        assert books[uid].watchlist_tickers == {"MSFT"}
        assert books[uid].total_value == Decimal("0")

    @pytest.mark.asyncio
    async def test_portfolio_only_user_has_empty_watchlist_tickers(self):
        uid = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([(_mock_position(ticker="AAPL"), uid)]),
                _watchlist_result([]),
            ]
        )

        books, sectors = await load_books(session)

        assert books[uid].held_tickers == {"AAPL"}
        assert books[uid].watchlist_tickers == set()
        assert sectors["AAPL"] == "Technology"

    @pytest.mark.asyncio
    async def test_user_with_both_gets_both_sets_populated(self):
        uid = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([(_mock_position(ticker="AAPL"), uid)]),
                _watchlist_result([("MSFT", uid)]),
            ]
        )

        books, sectors = await load_books(session)

        assert books[uid].held_tickers == {"AAPL"}
        assert books[uid].watchlist_tickers == {"MSFT"}

    @pytest.mark.asyncio
    async def test_watchlist_ticker_does_not_affect_sector_or_total_value(self):
        """Watchlist tickers have no shares/cost basis — they must not be
        folded into sector_values/total_value math, only into the separate
        watchlist_tickers set used purely for gating."""
        uid = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([(_mock_position(ticker="AAPL", purchase_price=Decimal("100"), quantity=Decimal("10")), uid)]),
                _watchlist_result([("MSFT", uid)]),
            ]
        )

        books, _sectors = await load_books(session)

        assert books[uid].total_value == Decimal("1000")
        assert "MSFT" not in books[uid].sector_values
        assert "MSFT" not in books[uid].positions

    @pytest.mark.asyncio
    async def test_multiple_watchlists_for_same_user_are_unioned(self):
        uid = uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([]),
                _watchlist_result([("MSFT", uid), ("GOOGL", uid), ("msft", uid)]),
            ]
        )

        books, _sectors = await load_books(session)

        assert books[uid].watchlist_tickers == {"MSFT", "GOOGL"}

    @pytest.mark.asyncio
    async def test_different_users_get_separate_books(self):
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[
                _positions_result([(_mock_position(ticker="AAPL"), uid1)]),
                _watchlist_result([("MSFT", uid2)]),
            ]
        )

        books, _sectors = await load_books(session)

        assert books[uid1].held_tickers == {"AAPL"}
        assert books[uid1].watchlist_tickers == set()
        assert books[uid2].held_tickers == set()
        assert books[uid2].watchlist_tickers == {"MSFT"}

    @pytest.mark.asyncio
    async def test_no_users_returns_empty_books(self):
        session = AsyncMock()
        session.execute = AsyncMock(
            side_effect=[_positions_result([]), _watchlist_result([])]
        )
        books, sectors = await load_books(session)
        assert books == {}
        assert sectors == {}
