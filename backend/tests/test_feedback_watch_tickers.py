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

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import feedback


def _mock_request(key: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        headers={"X-Internal-Key": key} if key else {},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def _rows_result(values: list) -> MagicMock:
    """Mock for db.execute(...) where the caller does result.all() directly
    (row tuples), not result.scalars().all()."""
    result = MagicMock()
    result.all.return_value = [(v,) for v in values]
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
    async def test_merges_and_dedupes_positions_and_filings(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _rows_result(["aapl", "SHMD"]),  # open positions
                _rows_result(["shmd", "TSLA"]),  # recent Form 4 filers
            ]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["AAPL", "SHMD", "TSLA"]}

    @pytest.mark.asyncio
    async def test_empty_when_no_positions_or_filings(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[_rows_result([]), _rows_result([])])
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": []}

    @pytest.mark.asyncio
    async def test_blank_tickers_skipped(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[_rows_result(["", None, "GME"]), _rows_result([])]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["GME"]}

    @pytest.mark.asyncio
    async def test_capped_at_watch_ticker_limit(self, monkeypatch):
        monkeypatch.setattr(feedback, "_INTERNAL_NEWS_KEY", "correct-key")
        monkeypatch.setattr(feedback, "_WATCH_TICKER_LIMIT", 3)
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[_rows_result(["AAA", "BBB", "CCC", "DDD"]), _rows_result([])]
        )
        result = await feedback.get_watch_tickers(_mock_request("correct-key"), db=db)
        assert result == {"tickers": ["AAA", "BBB", "CCC"]}
