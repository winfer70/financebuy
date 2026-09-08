"""
============================================================================
TEST SUITE: form13f_monitor (13F poller — CUSIP resolution + ticker filter)
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

from app.trading import form13f_monitor

ATOM_ONE_ENTRY = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>13F-HR - Some Fund LLC (0002152085) (Filer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2152085/x/0001085146-26-000764-index.htm"/>
<summary type="html">&lt;b&gt;AccNo:&lt;/b&gt; 0001085146-26-000764</summary>
<updated>2026-09-08T16:18:42-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="13F-HR"/>
<id>urn:tag:sec.gov,2008:accession-number=0001085146-26-000764</id>
</entry>
</feed>"""

INDEX_HTML = '<a href="/Archives/edgar/data/2152085/x/infotable.xml">infotable.xml</a>'

INFOTABLE_XML = """<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable>
    <nameOfIssuer>TRACKED CO</nameOfIssuer>
    <cusip>111111111</cusip>
    <value>500000</value>
    <shrsOrPrnAmt><sshPrnamt>1000</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>UNTRACKED CO</nameOfIssuer>
    <cusip>222222222</cusip>
    <value>900000</value>
    <shrsOrPrnAmt><sshPrnamt>2000</sshPrnamt></shrsOrPrnAmt>
  </infoTable>
</informationTable>"""


class _FakeFetcher:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, url: str) -> str:
        if "output=atom" in url:
            return ATOM_ONE_ENTRY
        if url.endswith("index.htm"):
            return INDEX_HTML
        if url.endswith("infotable.xml"):
            return INFOTABLE_XML
        raise ValueError(f"unexpected URL in test: {url}")


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await form13f_monitor.poll_13f_filings({})
    assert result == {"skipped": True, "reason": "no_user_agent"}


@pytest.mark.asyncio
async def test_poll_resolves_cusips_and_filters_to_tracked_tickers(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored)

    def _fake_resolve(cusips):
        return {"111111111": "TRKD", "222222222": "UNTRKD"}

    with (
        patch("app.trading.form13f_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form13f_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form13f_monitor._wanted_tickers", AsyncMock(return_value={"TRKD"})),
        patch("app.trading.form13f_monitor.resolve_cusips", side_effect=_fake_resolve),
    ):
        stats = await form13f_monitor.poll_13f_filings({})

    assert stats["fetched"] == 1
    assert stats["new"] == 1
    assert stats["holdings_seen"] == 2
    assert stats["matched"] == 1
    assert stats["stored"] == 1
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.ticker == "TRKD"
    assert added.cusip == "111111111"
    assert added.filer_name == "Some Fund LLC"
    assert float(added.shares) == 1000.0
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_skips_when_no_tracked_tickers(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()

    with (
        patch("app.trading.form13f_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form13f_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form13f_monitor._wanted_tickers", AsyncMock(return_value=set())),
    ):
        stats = await form13f_monitor.poll_13f_filings({})

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
        patch("app.trading.form13f_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form13f_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.form13f_monitor._wanted_tickers", AsyncMock(return_value={"TRKD"})),
    ):
        stats = await form13f_monitor.poll_13f_filings({})

    assert stats["new"] == 0
    assert stats["stored"] == 0
    session.add.assert_not_called()


class TestGetRecent13fHolders:
    @pytest.mark.asyncio
    async def test_empty_without_ticker(self):
        session = AsyncMock()
        assert await form13f_monitor.get_recent_13f_holders(session, "") == []
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_recent_rows(self):
        session = AsyncMock()
        row = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=result)

        found = await form13f_monitor.get_recent_13f_holders(session, "trkd")
        assert found == [row]
