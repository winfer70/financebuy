"""Tests for redesigned insider Telegram briefing (10b5-1, stake %, pattern, concern)."""
import os
from datetime import date

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-jwt-validation-purposes")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap")

from app.trading.insider_briefing import (
    PositionBrief,
    concern_level,
    format_insider_telegram,
    format_news_digest,
    summarize_owner_history,
)
from app.trading.insider_edgar import parse_form4_xml, stake_pct_sold

FORM4_SELL_10B5 = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000717540</issuerCik>
    <issuerTradingSymbol>SNDK</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>SHEK BERNARD</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>Chief Legal Officer &amp; Secty</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>1</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-09-02</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>600</value></transactionShares>
        <transactionPricePerShare><value>1525.60</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>49400</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

FORM4_SELL_DISCRETIONARY = FORM4_SELL_10B5.replace(
    "<aff10b5One>1</aff10b5One>", "<aff10b5One>0</aff10b5One>"
).replace(
    "<sharesOwnedFollowingTransaction><value>49400</value>",
    "<sharesOwnedFollowingTransaction><value>1400</value>",
).replace(
    "<officerTitle>Chief Legal Officer &amp; Secty</officerTitle>",
    "<officerTitle>CFO</officerTitle>",
)

SNAP = {
    "vol_ratio": 0.6,
    "price_up": False,
    "leaving": False,
    "sector": "Technology",
    "sector_etf": "XLK",
    "sector_vol_ratio": 0.7,
    "sector_price_up": False,
}
NEWS = [
    {"title": "MSCI World inclusion", "score": 3, "label": "BULL", "severity": "med", "source": "yahoo", "reasoning": ""},
    {"title": "Moody's Ba1 upgrade", "score": 2, "label": "BULL", "severity": "med", "source": "mw", "reasoning": ""},
    {"title": "Kioxia $31B Japan investment", "score": 2, "label": "BULL", "severity": "med", "source": "yahoo", "reasoning": ""},
    {"title": "Bernstein reiterated Buy", "score": 2, "label": "BULL", "severity": "low", "source": "google", "reasoning": ""},
]


def test_parse_aff10b5_one_and_stake_pct():
    rows = parse_form4_xml(FORM4_SELL_10B5, accession="0000717540-26-000001")
    assert len(rows) == 1
    r = rows[0]
    assert r["is_10b5_1"] is True
    assert r["shares"] == 600
    assert r["shares_after"] == 49400
    assert abs(r["stake_pct"] - (600 / 50000)) < 1e-9
    assert r["officer_title"] == "Chief Legal Officer & Secty"


def test_parse_aff10b5_false_and_large_stake():
    rows = parse_form4_xml(FORM4_SELL_DISCRETIONARY)
    r = rows[0]
    assert r["is_10b5_1"] is False
    assert r["stake_pct"] == stake_pct_sold(600, 1400)
    assert abs(r["stake_pct"] - 0.3) < 1e-9


def test_owner_pattern_scheduled():
    prior = [
        {"transaction_date": "2025-12-01", "shares": 600},
        {"transaction_date": "2026-02-01", "shares": 600},
        {"transaction_date": "2026-04-01", "shares": 601},
        {"transaction_date": "2026-06-01", "shares": 600},
    ]
    p = summarize_owner_history(prior, current_shares=600, current_date=date(2026, 9, 2))
    assert p.count == 5
    assert p.ordinal == "5th"
    assert abs(p.avg_shares - 600.2) < 1
    assert p.avg_interval_days is not None
    assert p.looks_scheduled is True


def test_concern_low_for_10b5_small_stake():
    filing = parse_form4_xml(FORM4_SELL_10B5)[0]
    assert concern_level(filing, cluster_count=1) == "LOW"


def test_concern_high_for_cfo_discretionary_dump_cluster():
    filing = parse_form4_xml(FORM4_SELL_DISCRETIONARY)[0]
    assert concern_level(filing, cluster_count=3) == "HIGH"


def test_news_digest_distinguishes_empty_vs_error():
    empty = format_news_digest([], status="empty")
    assert "0 articles" in empty[0]
    assert "checked" in empty[0]
    err = format_news_digest([], status="error")
    assert "could not query" in err[0]
    ok = format_news_digest(NEWS, status="ok")
    assert "4 articles" in ok[0]
    assert "MSCI" in ok[1]


def test_telegram_template_shek_style():
    filing = parse_form4_xml(FORM4_SELL_10B5)[0]
    filing["filing_url"] = "https://www.sec.gov/Archives/example.xml"
    pattern = summarize_owner_history(
        [
            {"transaction_date": "2025-12-05", "shares": 600},
            {"transaction_date": "2026-02-01", "shares": 600},
            {"transaction_date": "2026-04-01", "shares": 600},
            {"transaction_date": "2026-06-01", "shares": 600},
            {"transaction_date": "2026-09-02", "shares": 600},
        ]
    )
    title, body = format_insider_telegram(
        filing,
        snap=SNAP,
        news=NEWS,
        news_status="ok",
        cluster_count=1,
        cluster_kind="sellers",
        pattern=pattern,
        position=PositionBrief(quantity=2, purchase_price=1535.0, soft_stop=1420.0),
        notional=915360.0,
    )
    assert "LOW concern" in title
    assert "SNDK" in title
    assert "$915,360" in title
    assert "10b5-1 plan: YES" in body
    assert "Stake sold: 1.2%" in body
    assert "Pattern:" in body
    assert "Your position: 2 sh, BEP $1,535.00, stop $1,420.00" in body
    assert "4 articles" in body
    assert "MSCI" in body
    assert "Filing:" in body
    assert "Volume" in body
