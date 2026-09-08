"""
============================================================================
TEST SUITE: GET /api/v1/feedback/internal/watch-tickers
============================================================================

Covers the endpoint that hands the news worker a targeted watchlist (open
positions + recent Form 4 filers) so it can search for tickers that general
RSS feeds rarely mention by name. See PROJECT memory / this session's fix
for why this exists: insider Telegram alerts were showing "0 articles
scored" for tickers the worker had no way to ever encounter organically.
============================================================================
"""
import os

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import feedback


def _mock_request(key: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        headers={"X-Internal-Key": key} if key else {},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _held_result(tickers: list) -> MagicMock:
    """Mock for the open-positions query: result.all() -> [(ticker,), ...]."""
    result = MagicMock()
    result.all.return_value = [(t,) for t in tickers]
    return result


def _filed_result(pairs: list) -> MagicMock:
    """Mock for the Form 4 filers query: result.all() ->
    [(ticker, latest_transaction_date), ...], already in the recency-desc
    order the real GROUP BY / ORDER BY query would return."""
    result = MagicMock()
    result.all.return_value = list(pairs)
    return result


class TestAuth:
    @pytest.mark.asyncio
    async def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        with pytest.raises(Exception) as exc_info:
            await feedback.get_watch_tickers(_mock_request(""), db=db)
        assert getattr(exc_info.value, "status_code", None) == 403

    @pytest.mark.asyncio
    async def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        with pytest.raises(Exception) as exc_info:
            await feedback.get_watch_tickers(_mock_request("wrong-key"), db=db)
        assert getattr(exc_info.value, "status_code", None) == 403

    @pytest.mark.asyncio
    async def test_no_key_configured_rejects_everything(self, monkeypatch):
        # _INTERNAL_NEWS_KEY == "" is the out-of-the-box state — must fail
        # closed rather than allow any request through.
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "")
        db = AsyncMock()
        with pytest.raises(Exception) as exc_info:
            await feedback.get_watch_tickers(_mock_request("anything"), db=db)
        assert getattr(exc_info.value, "status_code", None) == 403


class TestWatchTickerAggregation:
    @pytest.mark.asyncio
    async def test_filed_tickers_ordered_most_recent_first(self, monkeypatch):
        # Regression test: GPUS (a brand-new filing) was ranking behind
        # alphabetically-earlier tickers and never getting searched under the
        # old plain-alphabetical ordering. Most recent filing must lead.
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _held_result([]),  # open positions
                _filed_result([  # already recency-desc, as the real query returns
                    ("gpus", date(2026, 9, 4)),
                    ("aapl", date(2026, 8, 20)),
                ]),
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["GPUS", "AAPL"]}

    @pytest.mark.asyncio
    async def test_held_tickers_appended_after_filed(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _held_result(["msft"]),
                _filed_result([("shmd", date(2026, 9, 1))]),
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["SHMD", "MSFT"]}

    @pytest.mark.asyncio
    async def test_dedupes_ticker_held_and_filed(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _held_result(["shmd"]),
                _filed_result([("SHMD", date(2026, 9, 1)), ("TSLA", date(2026, 8, 1))]),
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        # SHMD keeps its (higher-priority) position from the filed list;
        # the held-list duplicate is dropped rather than appended again.
        assert result == {"tickers": ["SHMD", "TSLA"]}

    @pytest.mark.asyncio
    async def test_empty_when_no_positions_or_filings(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_held_result([]), _filed_result([])])
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": []}

    @pytest.mark.asyncio
    async def test_blank_tickers_skipped(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _held_result(["", None, "GME"]),
                _filed_result([]),
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["GME"]}

    @pytest.mark.asyncio
    async def test_capped_at_watch_ticker_limit(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        monkeypatch.setattr(feedback, "_WATCH_TICKER_LIMIT", 3)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _held_result([]),
                _filed_result([
                    ("AAA", date(2026, 9, 4)),
                    ("BBB", date(2026, 9, 3)),
                    ("CCC", date(2026, 9, 2)),
                    ("DDD", date(2026, 9, 1)),
                ]),
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["AAA", "BBB", "CCC"]}
