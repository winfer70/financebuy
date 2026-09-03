"""Unit tests for Form 4 XML/atom parse and the insider Telegram gate."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-jwt-validation-purposes")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap")

from decimal import Decimal

from app.trading.insider_edgar import parse_atom_accessions, parse_form4_xml, xml_doc_url_from_index_html
from app.trading.market_context import format_insider_report
from app.trading.insider_gate import BookSnapshot, GateResult, Integrity, evaluate_filing, sector_exposure


FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0000320193</issuerCik>
    <issuerTradingSymbol>AAPL</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001214156</rptOwnerCik>
      <rptOwnerName>COOK TIMOTHY</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector>
      <isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-09-01</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>2000</value></transactionShares>
        <transactionPricePerShare><value>150.00</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>4 - COOK TIMOTHY (0001214156) (Reporting)</title>
    <link href="https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.htm"/>
    <updated>2026-09-02T12:00:00-04:00</updated>
  </entry>
</feed>
"""


def _book(**kwargs):
    base = dict(
        total_value=Decimal("1000000"),
        sector_values={"Technology": Decimal("200000")},
        held_tickers=set(),
        avoid_tickers={"OGN"},
        sector_cap=Decimal("0.30"),
        min_buy_usd=Decimal("25000"),
    )
    base.update(kwargs)
    return BookSnapshot(**base)


def test_parse_form4_open_market_buy():
    rows = parse_form4_xml(FORM4, accession="0000320193-26-000123")
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "AAPL"
    assert r["transaction_code"] == "P"
    assert r["is_officer"] is True
    assert r["officer_title"] == "CEO"
    assert r["shares"] == 2000
    assert r["price"] == 150.0
    assert r["is_10b5_1"] is None


def test_parse_form4_10b5_footnote():
    xml = FORM4.replace("</ownershipDocument>", "<footnotes><footnote>Sale pursuant to Rule 10b5-1 plan.</footnote></footnotes></ownershipDocument>")
    rows = parse_form4_xml(xml)
    assert rows[0]["is_10b5_1"] is True


def test_parse_atom_accession():
    entries = parse_atom_accessions(ATOM)
    assert entries[0]["accession"] == "0000320193-26-000123"


def test_gate_officer_buy_passes():
    filing = parse_form4_xml(FORM4)[0]
    g = evaluate_filing(filing, _book(), ticker_sector="Technology", cluster_count=1)
    assert g.worth_telegram is True
    assert g.event_type == "insider_buy"
    assert g.notional == Decimal("300000")


def test_gate_blocks_avoid_list():
    filing = parse_form4_xml(FORM4)[0]
    filing["ticker"] = "OGN"
    g = evaluate_filing(filing, _book(), ticker_sector="Healthcare")
    assert g.worth_telegram is False
    assert "avoid_tickers" in g.reasons[0]


def test_gate_blocks_sector_cap():
    filing = parse_form4_xml(FORM4)[0]
    book = _book(sector_values={"Technology": Decimal("400000")})
    g = evaluate_filing(filing, book, ticker_sector="Technology")
    assert g.worth_telegram is False
    assert g.severity == "warning"
    assert "sector" in g.reasons[0]


def test_gate_blocks_10b5():
    filing = parse_form4_xml(FORM4)[0]
    filing["is_10b5_1"] = True
    g = evaluate_filing(filing, _book(), ticker_sector="Technology")
    assert g.worth_telegram is False


def test_gate_blocks_tiny_notional():
    filing = parse_form4_xml(FORM4)[0]
    filing["shares"] = 1
    filing["price"] = 10
    g = evaluate_filing(filing, _book(), ticker_sector="Technology")
    assert g.worth_telegram is False


def test_gate_ten_percent_only_needs_cluster():
    filing = parse_form4_xml(FORM4)[0]
    filing["is_officer"] = False
    filing["is_director"] = False
    filing["is_ten_percent"] = True
    g = evaluate_filing(filing, _book(), ticker_sector="Technology", cluster_count=1)
    assert g.worth_telegram is False
    g2 = evaluate_filing(filing, _book(), ticker_sector="Technology", cluster_count=3)
    assert g2.worth_telegram is True
    assert g2.event_type == "insider_cluster"


def test_gate_sell_held_is_critical():
    filing = parse_form4_xml(FORM4)[0]
    filing["transaction_code"] = "S"
    filing["is_10b5_1"] = False
    g = evaluate_filing(filing, _book(held_tickers={"AAPL"}), ticker_sector="Technology")
    assert g.worth_telegram is True
    assert g.severity == "critical"
    assert g.event_type == "insider_sell"


def test_gate_sell_held_10b5_small_stake_is_info():
    filing = parse_form4_xml(FORM4)[0]
    filing["transaction_code"] = "S"
    filing["is_10b5_1"] = True
    filing["stake_pct"] = 0.012
    g = evaluate_filing(filing, _book(held_tickers={"AAPL"}), ticker_sector="Technology")
    assert g.worth_telegram is True
    assert g.severity == "info"


def test_gate_sell_unheld_is_silent():
    filing = parse_form4_xml(FORM4)[0]
    filing["transaction_code"] = "S"
    g = evaluate_filing(filing, _book(), ticker_sector="Technology")
    assert g.worth_telegram is False
    assert g.in_app is False


def test_gate_critical_de_blocks_buy():
    filing = parse_form4_xml(FORM4)[0]
    g = evaluate_filing(
        filing, _book(), ticker_sector="Technology", integrity=Integrity(debt_to_equity=600)
    )
    assert g.worth_telegram is False


INDEX_HTML = """<html><body>
<a href="xslF345X05/wk-form4.xml">Print</a>
<a href="wk-form4.xml">wk-form4.xml</a>
</body></html>
"""
INDEX_URL = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/0000320193-26-000123-index.htm"


def test_xml_url_skips_xsl_and_joins_relative():
    url = xml_doc_url_from_index_html(INDEX_HTML, "0000320193-26-000123", INDEX_URL)
    assert url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/wk-form4.xml"


def test_xml_url_absolute_archives_path():
    html = '<a href="/Archives/edgar/data/320193/000032019326000123/own.xml">x</a>'
    url = xml_doc_url_from_index_html(html, "0000320193-26-000123")
    assert url == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000123/own.xml"


def test_xml_url_empty_when_only_xsl():
    html = '<a href="xslF345X05/wk-form4.xml">print</a>'
    assert xml_doc_url_from_index_html(html, "0000320193-26-000123", INDEX_URL) == ""


def test_format_insider_report_includes_filing_volume_and_news():
    filing = parse_form4_xml(FORM4)[0]
    filing["filing_url"] = "https://www.sec.gov/Archives/example.xml"
    filing["is_10b5_1"] = False
    snap = {
        "vol_ratio": 2.4,
        "price_up": False,
        "leaving": True,
        "sector": "Technology",
        "sector_etf": "XLK",
        "sector_vol_ratio": 1.1,
        "sector_price_up": False,
    }
    news = [
        {
            "title": "Supplier cuts guidance",
            "score": -3,
            "label": "BEAR",
            "severity": "med",
            "source": "yahoo",
            "reasoning": "guidance cut",
        }
    ]
    body = format_insider_report(
        filing,
        ["open-market buy by CEO"],
        snap,
        news,
        cluster_count=1,
        sector_pct=0.20,
        sector_cap=0.30,
        ticker_sector="Technology",
        notional=300000,
    )
    assert "COOK TIMOTHY" in body
    assert "CEO" in body
    assert "20%" in body
    assert "LEAVING" in body or "2.4" in body
    assert "Supplier cuts" in body or "BEAR" in body
    assert "Filing:" in body
    assert "Advice" in body
    assert "10b5-1" in body
    assert "Your position:" in body


def test_sector_exposure_uses_gics_not_is_semi():
    exp = sector_exposure(
        [
            {"sector": "Technology", "market_value": 200},
            {"sector": "Energy", "market_value": 50},
        ],
        Decimal("250"),
    )
    assert exp["Technology"] == Decimal("200")
    assert "semi" not in exp
