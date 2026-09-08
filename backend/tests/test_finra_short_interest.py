"""
============================================================================
TEST SUITE: finra_short_interest (FINRA biweekly short-interest ingestion)
============================================================================

Covers _find_latest_settlement_date (HEAD-scan discovery), _parse_and_filter
(pipe-delimited CSV parsing against a real sample row set), poll_short_interest
(the full cycle with mocked HTTP/session), and get_latest_short_interest
(the lookup insider_monitor.py calls for squeeze/crowding advice context).
============================================================================
"""
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.trading import finra_short_interest as fsi

SAMPLE_CSV = (
    "accountingYearMonthNumber|symbolCode|issueName|issuerServicesGroupExchangeCode|"
    "marketClassCode|currentShortPositionQuantity|previousShortPositionQuantity|"
    "stockSplitFlag|averageDailyVolumeQuantity|daysToCoverQuantity|revisionFlag|"
    "changePercent|changePreviousNumber|settlementDate\n"
    "20260814|A|Agilent Technologies Inc.|A|NYSE|5170553|5749623||1369994|3.77||-10.07|-579070|2026-08-14\n"
    "20260814|AAPL|Apple Inc.|A|NNM|34636195|39059449||38275532|1.0||-11.32|-4423254|2026-08-14\n"
    "20260814|ZZZZ|Random Penny Stock|E|OTC|100|100||100|1.0||0.00|0|2026-08-14\n"
)


@pytest.fixture(autouse=True)
def _reset_cache():
    fsi._cached_settlement_date_str = None
    fsi._cache_checked_on = None
    yield
    fsi._cached_settlement_date_str = None
    fsi._cache_checked_on = None


class TestParseAndFilter:
    def test_keeps_only_wanted_tickers(self):
        rows = fsi._parse_and_filter(SAMPLE_CSV, {"AAPL"})
        assert len(rows) == 1
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["current_short_position"] == "34636195"
        assert rows[0]["days_to_cover"] == "1.0"
        assert rows[0]["settlement_date"] == "2026-08-14"

    def test_empty_wanted_set_returns_nothing(self):
        assert fsi._parse_and_filter(SAMPLE_CSV, set()) == []

    def test_matches_multiple_wanted_tickers(self):
        rows = fsi._parse_and_filter(SAMPLE_CSV, {"AAPL", "A", "ZZZZ"})
        assert {r["ticker"] for r in rows} == {"AAPL", "A", "ZZZZ"}

    def test_empty_csv_returns_nothing(self):
        assert fsi._parse_and_filter("", {"AAPL"}) == []

    def test_missing_required_columns_returns_nothing(self):
        bad_csv = "foo|bar\nx|y\n"
        assert fsi._parse_and_filter(bad_csv, {"AAPL"}) == []


class TestToDecimal:
    def test_valid_number(self):
        from decimal import Decimal

        assert fsi._to_decimal("3.77") == Decimal("3.77")

    def test_blank_returns_none(self):
        assert fsi._to_decimal("") is None
        assert fsi._to_decimal("  ") is None

    def test_garbage_returns_none(self):
        assert fsi._to_decimal("not-a-number") is None


class TestFindLatestSettlementDate:
    def test_returns_first_date_that_resolves(self):
        # Only "today" (whatever that is when the test runs) resolves —
        # proves the scan takes the *first* hit, not some arbitrary one.
        today_str = date.today().strftime("%Y%m%d")

        def _head(url, timeout=None):
            resp = MagicMock()
            resp.status_code = 200 if today_str in url else 403
            return resp

        with patch("app.trading.finra_short_interest.requests.head", side_effect=_head):
            found = fsi._find_latest_settlement_date()
        assert found == today_str

    def test_none_when_nothing_found_in_lookback_window(self):
        resp = MagicMock()
        resp.status_code = 403
        with patch("app.trading.finra_short_interest.requests.head", return_value=resp):
            assert fsi._find_latest_settlement_date() is None

    def test_network_error_is_skipped_not_raised(self):
        import requests as _requests

        with patch(
            "app.trading.finra_short_interest.requests.head",
            side_effect=_requests.RequestException("boom"),
        ):
            assert fsi._find_latest_settlement_date() is None

    def test_second_call_same_day_uses_cache(self):
        resp = MagicMock()
        resp.status_code = 200
        mock_head = MagicMock(return_value=resp)
        with patch("app.trading.finra_short_interest.requests.head", mock_head):
            fsi._find_latest_settlement_date()
            fsi._find_latest_settlement_date()
        assert mock_head.call_count == 1


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _rows_result(values):
    result = MagicMock()
    result.all.return_value = [(v,) for v in values]
    return result


class TestPollShortInterest:
    @pytest.mark.asyncio
    async def test_no_file_found_returns_early(self):
        with patch("app.trading.finra_short_interest._find_latest_settlement_date", return_value=None):
            result = await fsi.poll_short_interest({})
        assert result == {"found": False}

    @pytest.mark.asyncio
    async def test_no_tracked_tickers_skips_fetch(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[_rows_result([]), _rows_result([])])

        with (
            patch("app.trading.finra_short_interest._find_latest_settlement_date", return_value="20260814"),
            patch("app.trading.finra_short_interest._SessionLocal", _session_cm(session)),
            patch("app.trading.finra_short_interest._fetch_csv") as mock_fetch,
        ):
            result = await fsi.poll_short_interest({})

        mock_fetch.assert_not_called()
        assert result["matched"] == 0

    @pytest.mark.asyncio
    async def test_stores_matched_rows_and_dedupes(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(
            side_effect=[_rows_result(["AAPL"]), _rows_result([]), already_stored]
        )

        with (
            patch("app.trading.finra_short_interest._find_latest_settlement_date", return_value="20260814"),
            patch("app.trading.finra_short_interest._SessionLocal", _session_cm(session)),
            patch("app.trading.finra_short_interest._fetch_csv", return_value=SAMPLE_CSV),
        ):
            result = await fsi.poll_short_interest({})

        assert result["matched"] == 1
        assert result["stored"] == 1
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.ticker == "AAPL"
        assert added.settlement_date == date(2026, 8, 14)
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_already_stored_ticker_settlement_pair(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = "existing-id"
        session.execute = AsyncMock(
            side_effect=[_rows_result(["AAPL"]), _rows_result([]), already_stored]
        )

        with (
            patch("app.trading.finra_short_interest._find_latest_settlement_date", return_value="20260814"),
            patch("app.trading.finra_short_interest._SessionLocal", _session_cm(session)),
            patch("app.trading.finra_short_interest._fetch_csv", return_value=SAMPLE_CSV),
        ):
            result = await fsi.poll_short_interest({})

        assert result["stored"] == 0
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_gracefully(self):
        session = AsyncMock()
        session.execute = AsyncMock(side_effect=[_rows_result(["AAPL"]), _rows_result([])])

        with (
            patch("app.trading.finra_short_interest._find_latest_settlement_date", return_value="20260814"),
            patch("app.trading.finra_short_interest._SessionLocal", _session_cm(session)),
            patch("app.trading.finra_short_interest._fetch_csv", return_value=None),
        ):
            result = await fsi.poll_short_interest({})

        assert result["matched"] == 0
        assert result["stored"] == 0


class TestGetLatestShortInterest:
    @pytest.mark.asyncio
    async def test_none_without_ticker(self):
        session = AsyncMock()
        assert await fsi.get_latest_short_interest(session, "") is None
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_most_recent_snapshot(self):
        session = AsyncMock()
        snapshot = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = snapshot
        session.execute = AsyncMock(return_value=result)

        found = await fsi.get_latest_short_interest(session, "aapl")
        assert found is snapshot

    @pytest.mark.asyncio
    async def test_none_when_nothing_on_file(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        assert await fsi.get_latest_short_interest(session, "AAPL") is None
