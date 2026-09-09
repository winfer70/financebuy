"""
============================================================================
TEST SUITE: form8k_monitor (8-K poller — ticker filter + market-color lookup)
============================================================================
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault(
    "JWT_SECRET",
    "test-secret-key-that-is-long-enough-for-jwt-validation-purposes",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest

from app.trading import form8k_monitor

ATOM_TWO_ENTRIES = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>8-K - Tracked Co (0001111111) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1111111/x/0001111111-26-000001-index.htm"/>
<summary type="html">&lt;b&gt;AccNo:&lt;/b&gt; 0001111111-26-000001
&lt;br&gt;Item 5.02: Departure of Directors or Certain Officers</summary>
<updated>2026-09-08T17:29:43-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0001111111-26-000001</id>
</entry>
<entry>
<title>8-K - Untracked Co (0002222222) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2222222/x/0002222222-26-000002-index.htm"/>
<summary type="html">&lt;b&gt;AccNo:&lt;/b&gt; 0002222222-26-000002
&lt;br&gt;Item 8.01: Other Events</summary>
<updated>2026-09-08T17:30:00-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="8-K"/>
<id>urn:tag:sec.gov,2008:accession-number=0002222222-26-000002</id>
</entry>
</feed>"""


class _FakeFetcher:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, url: str) -> str:
        return ATOM_TWO_ENTRIES


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await form8k_monitor.poll_8k_filings({})
    assert result == {"skipped": True, "reason": "no_user_agent"}


@pytest.mark.asyncio
async def test_poll_filters_to_tracked_tickers_only(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored)

    def _fake_resolve(cik):
        return {"0001111111": "TRKD"}.get(cik)  # only the first CIK resolves/is tracked

    with (
        patch("app.trading.form8k_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form8k_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form8k_monitor._wanted_tickers", AsyncMock(return_value={"TRKD"})),
        patch("app.trading.form8k_monitor.resolve_ticker", side_effect=_fake_resolve),
    ):
        stats = await form8k_monitor.poll_8k_filings({})

    assert stats["fetched"] == 2
    assert stats["matched"] == 1
    assert stats["stored"] == 1
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.ticker == "TRKD"
    assert added.items == [{"code": "5.02", "description": "Departure of Directors or Certain Officers"}]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_skips_when_no_tracked_tickers(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()

    with (
        patch("app.trading.form8k_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form8k_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form8k_monitor._wanted_tickers", AsyncMock(return_value=set())),
    ):
        stats = await form8k_monitor.poll_8k_filings({})

    assert stats["matched"] == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_poll_skips_already_stored_accession(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = "existing-id"
    session.execute = AsyncMock(return_value=already_stored)

    with (
        patch("app.trading.form8k_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form8k_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form8k_monitor._wanted_tickers", AsyncMock(return_value={"TRKD"})),
        patch("app.trading.form8k_monitor.resolve_ticker", return_value="TRKD"),
    ):
        stats = await form8k_monitor.poll_8k_filings({})

    assert stats["stored"] == 0
    session.add.assert_not_called()


class TestGetRecent8kFilings:
    @pytest.mark.asyncio
    async def test_empty_without_ticker(self):
        session = AsyncMock()
        assert await form8k_monitor.get_recent_8k_filings(session, "") == []
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_recent_rows(self):
        session = AsyncMock()
        row = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=result)

        found = await form8k_monitor.get_recent_8k_filings(session, "trkd")
        assert found == [row]
