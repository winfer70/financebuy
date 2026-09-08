"""
============================================================================
TEST SUITE: schedule13_monitor (13D/13G poller + ticker-wide lookup)
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

from app.trading import schedule13_monitor

def _atom(accession: str, form: str) -> str:
    return f"""<?xml version="1.0" encoding="ISO-8859-1"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
<title>SCHEDULE {form} - Test Issuer (0001840416) (Subject)</title>
<link rel="alternate" type="text/html" href="https://www.sec.gov/Archives/edgar/data/1840416/{accession.replace('-', '')}/{accession}-index.htm"/>
<updated>2026-09-08T18:10:09-04:00</updated>
<category scheme="https://www.sec.gov/" label="form type" term="SCHEDULE {form}"/>
<id>urn:tag:sec.gov,2008:accession-number={accession}</id>
</entry>
</feed>"""


ACC_13D = "0001213900-26-098095"
ACC_13G = "0001796651-26-000005"

INDEX_HTML_13D = f'<a href="/Archives/edgar/data/1840416/{ACC_13D.replace("-", "")}/primary_doc_13d.xml">primary_doc.xml</a>'
INDEX_HTML_13G = f'<a href="/Archives/edgar/data/1840416/{ACC_13G.replace("-", "")}/primary_doc_13g.xml">primary_doc.xml</a>'

FILING_13D_XML = """<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D">
  <headerData><submissionType>SCHEDULE 13D</submissionType>
    <filerInfo><filer><filerCredentials><cik>0001842872</cik></filerCredentials></filer></filerInfo>
  </headerData>
  <formData>
    <coverPageHeader>
      <dateOfEvent>08/31/2026</dateOfEvent>
      <issuerInfo><issuerCIK>0001840416</issuerCIK><issuerName>Test Issuer</issuerName></issuerInfo>
    </coverPageHeader>
    <reportingPersons>
      <reportingPersonInfo>
        <reportingPersonCIK>0001842872</reportingPersonCIK>
        <reportingPersonName>Someone</reportingPersonName>
        <aggregateAmountOwned>93633.00</aggregateAmountOwned>
        <percentOfClass>5.5</percentOfClass>
      </reportingPersonInfo>
    </reportingPersons>
  </formData>
</edgarSubmission>"""

FILING_13G_XML = """<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
  <headerData><submissionType>SCHEDULE 13G</submissionType>
    <filerInfo><filer><filerCredentials><cik>0001796651</cik></filerCredentials></filer></filerInfo>
  </headerData>
  <formData>
    <coverPageHeader>
      <eventDateRequiresFilingThisStatement>08/31/2026</eventDateRequiresFilingThisStatement>
      <issuerInfo><issuerCik>0001840416</issuerCik><issuerName>Test Issuer</issuerName></issuerInfo>
    </coverPageHeader>
    <coverPageHeaderReportingPersonDetails>
      <reportingPersonName>Some Fund LLC</reportingPersonName>
      <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>5830289.00</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
      <classPercent>6.2</classPercent>
    </coverPageHeaderReportingPersonDetails>
  </formData>
</edgarSubmission>"""


class _FakeFetcher:
    def __init__(self, *_args, **_kwargs):
        pass

    async def get(self, url: str) -> str:
        if "output=atom" in url:
            if "13D" in url:
                return _atom(ACC_13D, "13D")
            return _atom(ACC_13G, "13G")
        if url.endswith("index.htm"):
            return INDEX_HTML_13D if ACC_13D.replace("-", "") in url else INDEX_HTML_13G
        if url.endswith("primary_doc_13d.xml"):
            return FILING_13D_XML
        if url.endswith("primary_doc_13g.xml"):
            return FILING_13G_XML
        raise ValueError(f"unexpected URL in test: {url}")


def _session_cm(session):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await schedule13_monitor.poll_schedule13_filings({})
    assert result == {"skipped": True, "reason": "no_user_agent"}


@pytest.mark.asyncio
async def test_poll_stores_rows_from_both_feeds(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "TickerTap Test test@example.com")
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    already_stored = MagicMock()
    already_stored.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=already_stored)

    with (
        patch("app.trading.schedule13_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.schedule13_monitor._SessionLocal", _session_cm(session)),
        patch("app.trading.schedule13_monitor.resolve_ticker", return_value="TEST"),
    ):
        stats = await schedule13_monitor.poll_schedule13_filings({})

    # One accession fetched per feed (13D + 13G), each with one reporting person.
    assert stats["fetched"] == 2
    assert stats["new"] == 2
    assert stats["stored"] == 2
    assert stats["errors"] == 0
    assert session.add.call_count == 2
    added_13d = session.add.call_args_list[0][0][0]
    added_13g = session.add.call_args_list[1][0][0]
    assert added_13d.ticker == "TEST" and added_13d.filer_name == "Someone" and added_13d.is_13d is True
    assert added_13g.ticker == "TEST" and added_13g.filer_name == "Some Fund LLC" and added_13g.is_13d is False
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
        patch("app.trading.schedule13_monitor.EdgarFetcher", _FakeFetcher),
        patch("app.trading.schedule13_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await schedule13_monitor.poll_schedule13_filings({})

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
                if "13D" in url:
                    return _atom(ACC_13D, "13D")
                return _atom(ACC_13G, "13G")
            raise RuntimeError("network blew up mid-filing")

    with (
        patch("app.trading.schedule13_monitor.EdgarFetcher", _BrokenFetcher),
        patch("app.trading.schedule13_monitor._SessionLocal", _session_cm(session)),
    ):
        stats = await schedule13_monitor.poll_schedule13_filings({})

    assert stats["errors"] == 2  # one per feed
    assert stats["stored"] == 0
    session.commit.assert_awaited_once()


class TestGetRecentBeneficialOwnership:
    @pytest.mark.asyncio
    async def test_empty_without_ticker(self):
        session = AsyncMock()
        assert await schedule13_monitor.get_recent_beneficial_ownership(session, "") == []
        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_recent_rows(self):
        session = AsyncMock()
        row = MagicMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=result)

        found = await schedule13_monitor.get_recent_beneficial_ownership(session, "aapl")
        assert found == [row]

    @pytest.mark.asyncio
    async def test_empty_when_nothing_on_file(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result)

        assert await schedule13_monitor.get_recent_beneficial_ownership(session, "AAPL") == []
