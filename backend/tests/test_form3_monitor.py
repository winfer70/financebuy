"""
============================================================================
TEST SUITE: form3_monitor (Form 3 poller + Form 4 sell baseline lookup)
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

from app.trading import form3_monitor

ATOM_TWO_ENTRIES = """<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>3 - PEARLMAN ANDREW SHAWN (0002153290) (Reporting)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/2153290/000121390026098148/0001213900-26-098148-index.htm"/>
<updated>2026-09-08T18:10:09-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="3"/>
<id>urn:tag:sec.gov,2008:accession-number=0001213900-26-098148</id>
</entry>
<entry>
<title>3 - First Breach, Inc. (0001892704) (Issuer)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1892704/000121390026098148/0001213900-26-098148-index.htm"/>
<updated>2026-09-08T18:10:09-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="3"/>
<id>urn:tag:sec.gov,2008:accession-number=0001213900-26-098148</id>
</entry>
</feed>"""

INDEX_HTML = '<a href="/Archives/edgar/data/1892704/000121390026098148/marketforms-73956.xml">marketforms-73956.xml</a>'

FILING_XML = """<?xml version="1.0"?>
<ownershipDocument>
    <periodOfReport>2026-08-12</periodOfReport>
    <issuer>
        <issuerCik>0001892704</issuerCik>
        <issuerTradingSymbol>FBDT</issuerTradingSymbol>
    </issuer>
    <reportingOwner>
        <reportingOwnerId>
            <rptOwnerCik>0002153290</rptOwnerCik>
            <rptOwnerName>PEARLMAN ANDREW SHAWN</rptOwnerName>
        </reportingOwnerId>
        <reportingOwnerRelationship>
            <isDirector>true</isDirector>
            <isOfficer>false</isOfficer>
            <isTenPercentOwner>false</isTenPercentOwner>
        </reportingOwnerRelationship>
    </reportingOwner>
    <nonDerivativeTable>
        <nonDerivativeHolding>
            <postTransactionAmounts>
                <sharesOwnedFollowingTransaction><value>100</value></sharesOwnedFollowingTransaction>
            </postTransactionAmounts>
        </nonDerivativeHolding>
    </nonDerivativeTable>
    <ownerSignature><signatureDate>2026-09-08</signatureDate></ownerSignature>
</ownershipDocument>"""


class _FakeFetcher:
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


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await form3_monitor.poll_form3_filings({})
    assert result == {"skipped": True, "reason": "no_user_agent"}


@pytest.mark.asyncio
async def test_poll_stores_new_statement(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored)

    with (
        patch("app.trading.form3_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form3_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await form3_monitor.poll_form3_filings({})

    assert stats["fetched"] == 2
    assert stats["new"] == 1  # deduped to one accession
    assert stats["stored"] == 1
    assert stats["errors"] == 0
    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.ticker == "FBDT"
    assert added.owner_cik == "0002153290"
    assert float(added.shares_owned) == 100.0
    session.commit.assert_awaited_once()


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
        patch("app.trading.form3_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.form3_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await form3_monitor.poll_form3_filings({})

    assert stats["new"] == 0
    assert stats["stored"] == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_poll_continues_after_per_entry_error(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored)

    class _BrokenFetcher(_FakeFetcher):
        async def get(self, url: str) -> str:
            if "output=atom" in url:
                return ATOM_TWO_ENTRIES
            raise RuntimeError("network blew up mid-filing")

    with (
        patch("app.trading.form3_monitor.EdgarFetcher", _BrokenFetcher),
        patch("app.trading.form3_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await form3_monitor.poll_form3_filings({})

    assert stats["errors"] == 1
    assert stats["stored"] == 0
    session.commit.assert_awaited_once()


class TestGetForm3Baseline:
    @pytest.mark.asyncio
    async def test_returns_none_without_owner_cik_or_ticker(self):
        session = AsyncMock()
        assert await form3_monitor.get_form3_baseline(session, "", "AAPL") is None
        assert await form3_monitor.get_form3_baseline(session, "0001214156", "") is None
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_the_baseline_when_on_file(self):
        session = AsyncMock()
        baseline = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = baseline
        session.execute = AsyncMock(return_value=result)

        found = await form3_monitor.get_form3_baseline(session, "0001214156", "aapl")
        assert found is baseline

    @pytest.mark.asyncio
    async def test_none_when_nothing_on_file(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=result)

        assert await form3_monitor.get_form3_baseline(session, "0001214156", "AAPL") is None
