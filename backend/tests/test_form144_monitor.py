"""
============================================================================
TEST SUITE: form144_monitor (Form 144 poller + Form 4 sell correlation)
============================================================================

Covers poll_form144_filings() (fetch -> dedupe -> parse -> resolve ticker
-> store) with a fake EdgarFetcher/session, and get_recent_144_notice()
(the correlation lookup insider_monitor.py's sell-gate path calls to turn
"insider sold" into "insider sold, and pre-announced it via Form 144").
============================================================================
"""
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.trading import form144_monitor

ATOM_TWO_ENTRIES = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>144 - Circle Internet Group, Inc. (0001876042) (Subject)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1876042/000196858226000933/0001968582-26-000933-index.htm"/>
<updated>2026-09-08T17:17:46-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="144"/>
<id>urn:tag:sec.gov,2008:accession-number=0001968582-26-000933</id>
</entry>
<entry>
<title>144 - Allaire Jeremy (0001539940) (Reporting)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1539940/000196858226000933/0001968582-26-000933-index.htm"/>
<updated>2026-09-08T17:17:46-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="144"/>
<id>urn:tag:sec.gov,2008:accession-number=0001968582-26-000933</id>
</entry>
</feed>"""

INDEX_HTML = '<a href="/Archives/edgar/data/1876042/000196858226000933/primary_doc.xml">primary_doc.xml</a>'

FILING_XML = """<?xml version="1.0" encoding="UTF-8"?><own:edgarSubmission xmlns:own="http://www.sec.gov/edgar/ownership">
  <own:headerData><own:filerInfo><own:filer><own:filerCredentials>
    <own:cik>0001539940</own:cik>
  </own:filerCredentials></own:filer></own:filerInfo></own:headerData>
  <own:formData>
    <own:issuerInfo>
      <own:issuerCik>0001876042</own:issuerCik>
      <own:issuerName>Circle Internet Group, Inc.</own:issuerName>
      <own:nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>Jeremy Allaire</own:nameOfPersonForWhoseAccountTheSecuritiesAreToBeSold>
      <own:relationshipsToIssuer><own:relationshipToIssuer>Officer</own:relationshipToIssuer></own:relationshipsToIssuer>
    </own:issuerInfo>
    <own:securitiesInformation>
      <own:brokerOrMarketmakerDetails><own:name>J.P. Morgan Securities LLC</own:name></own:brokerOrMarketmakerDetails>
      <own:noOfUnitsSold>177701</own:noOfUnitsSold>
      <own:aggregateMarketValue>18134387</own:aggregateMarketValue>
      <own:approxSaleDate>09/08/2026</own:approxSaleDate>
    </own:securitiesInformation>
    <own:noticeSignature><own:noticeDate>09/08/2026</own:noticeDate></own:noticeSignature>
  </own:formData>
</own:edgarSubmission>"""


class _FakeFetcher:
    """Serves fixed content per URL — mirrors EdgarFetcher's interface
    without any real network I/O."""

    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, url: str) -> str:
        if "output=atom" in url:
            return ATOM_TWO_ENTRIES
        if url.endswith("index.htm"):
            return INDEX_HTML
        if url.endswith(".xml"):
            return FILING_XML
        raise ValueError(f"unexpected URL in test: {url}")


def _session_cm(session: AsyncMock):
    """_SessionLocal() is used as `async with _SessionLocal() as session:`."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await form144_monitor.poll_form144_filings({})
    assert result == {"skipped": True, "reason": "no_user_agent"}


@pytest.mark.asyncio
async def test_poll_stores_new_notice_with_resolved_ticker(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    # Nothing stored yet -> _already_stored() returns False for the one
    # deduped accession (both atom entries collapse to the same accession).
    already_stored_result = MagicMock()
    already_stored_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    with (
        patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form144_monitor.resolve_ticker", return_value="CRCL"),
    ):
        stats = await form144_monitor.poll_form144_filings({})

    assert stats["fetched"] == 2
    assert stats["new"] == 1  # deduped to one accession despite two atom entries
    assert stats["stored"] == 1
    assert stats["errors"] == 0
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.ticker == "CRCL"
    assert added.owner_cik == "0001539940"
    assert float(added.shares) == 177701.0
    assert added.approx_sale_date == date(2026, 9, 8)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_skips_already_stored_accession(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    already_stored_result = MagicMock()
    already_stored_result.scalar_one_or_none.return_value = "existing-row-id"
    session.execute = AsyncMock(return_value=already_stored_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    with (
        patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await form144_monitor.poll_form144_filings({})

    assert stats["new"] == 0
    assert stats["stored"] == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_poll_continues_after_per_entry_error(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    already_stored_result = MagicMock()
    already_stored_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored_result)
    session.commit = AsyncMock()
    session.add = MagicMock()

    class _BrokenFetcher(_FakeFetcher):
        async def get(self, url: str) -> str:
            if "output=atom" in url:
                return ATOM_TWO_ENTRIES
            raise RuntimeError("network blew up mid-filing")

    with (
        patch("app.trading.form144_monitor.EdgarFetcher", _BrokenFetcher),
        patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await form144_monitor.poll_form144_filings({})

    assert stats["errors"] == 1
    assert stats["stored"] == 0
    session.commit.assert_awaited_once()  # still commits whatever *did* succeed


def _fake_book(held_tickers=None, watchlist_tickers=None):
    from app.trading.insider_gate import BookSnapshot

    return BookSnapshot(
        total_value=Decimal("0"),
        sector_values={},
        held_tickers=held_tickers or set(),
        avoid_tickers=set(),
        watchlist_tickers=watchlist_tickers or set(),
    )


class TestPlannedSellAlert:
    """A Form 144 is a real SEC "planned sell" concept — a tracked ticker
    (portfolio position or watchlist item) now gets its own alert the
    moment the notice lands, not just after-the-fact context on a later
    Form 4 sale."""

    @pytest.mark.asyncio
    async def test_sends_planned_sell_alert_to_holder(self, monkeypatch):
        monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
        holder = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=already_stored)

        mock_notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

        with (
            patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
            patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
            patch("app.trading.form144_monitor.resolve_ticker", return_value="CRCL"),
            patch(
                "app.trading.form144_monitor.load_books",
                AsyncMock(return_value=({holder: _fake_book(held_tickers={"CRCL"})}, {})),
            ),
            patch("app.trading.form144_monitor.notify_soft_stop", mock_notify),
        ):
            stats = await form144_monitor.poll_form144_filings({})

        assert stats["notified"] == 1
        mock_notify.assert_awaited_once()
        kwargs = mock_notify.call_args.kwargs
        assert kwargs["user_id"] == holder
        assert kwargs["event_type"] == "planned_sell"
        assert "CRCL" in kwargs["title"]
        assert "You hold this position." in kwargs["body"]
        assert kwargs["metadata"] == {"source": "form144_monitor", "ticker": "CRCL"}

    @pytest.mark.asyncio
    async def test_sends_planned_sell_alert_to_watchlister_with_correct_wording(self, monkeypatch):
        monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
        watcher = uuid.uuid4()
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=already_stored)

        mock_notify = AsyncMock(return_value={"telegram": True, "ntfy": True, "in_app": True})

        with (
            patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
            patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
            patch("app.trading.form144_monitor.resolve_ticker", return_value="CRCL"),
            patch(
                "app.trading.form144_monitor.load_books",
                AsyncMock(return_value=({watcher: _fake_book(watchlist_tickers={"CRCL"})}, {})),
            ),
            patch("app.trading.form144_monitor.notify_soft_stop", mock_notify),
        ):
            await form144_monitor.poll_form144_filings({})

        kwargs = mock_notify.call_args.kwargs
        assert kwargs["user_id"] == watcher
        assert "on your watchlist" in kwargs["body"].lower()
        assert "you hold this position" not in kwargs["body"].lower()

    @pytest.mark.asyncio
    async def test_no_alert_when_ticker_not_tracked_by_anyone(self, monkeypatch):
        monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=already_stored)

        mock_notify = AsyncMock()

        with (
            patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
            patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
            patch("app.trading.form144_monitor.resolve_ticker", return_value="CRCL"),
            patch(
                "app.trading.form144_monitor.load_books",
                AsyncMock(return_value=({uuid.uuid4(): _fake_book(held_tickers={"MSFT"})}, {})),
            ),
            patch("app.trading.form144_monitor.notify_soft_stop", mock_notify),
        ):
            stats = await form144_monitor.poll_form144_filings({})

        assert stats["notified"] == 0
        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_alert_when_ticker_unresolved(self, monkeypatch):
        monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
        session = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        already_stored = MagicMock()
        already_stored.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=already_stored)

        mock_notify = AsyncMock()

        with (
            patch("app.trading.form144_monitor.EdgarFetcher", _FakeFetcher),
            patch("app.trading.form144_monitor._SessionLocal", _session_cm(session)),
            patch("app.trading.form144_monitor.resolve_ticker", return_value=None),
            patch(
                "app.trading.form144_monitor.load_books",
                AsyncMock(return_value=({uuid.uuid4(): _fake_book(held_tickers={"MSFT"})}, {})),
            ),
            patch("app.trading.form144_monitor.notify_soft_stop", mock_notify),
        ):
            stats = await form144_monitor.poll_form144_filings({})

        assert stats["notified"] == 0
        mock_notify.assert_not_called()


class TestGetRecent144Notice:
    @pytest.mark.asyncio
    async def test_returns_none_without_owner_cik_or_ticker(self):
        session = AsyncMock()
        assert await form144_monitor.get_recent_144_notice(session, "", "AAPL") is None
        assert await form144_monitor.get_recent_144_notice(session, "0001214156", "") is None
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_most_recent_notice_within_window(self):
        session = AsyncMock()
        notice = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = notice
        session.execute = AsyncMock(return_value=result)

        found = await form144_monitor.get_recent_144_notice(session, "0001214156", "aapl")
        assert found is notice
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_none_when_nothing_on_file(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        assert await form144_monitor.get_recent_144_notice(session, "0001214156", "AAPL") is None
