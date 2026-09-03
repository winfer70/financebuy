"""Template advice for Telegram briefs — rules + book, no LLM."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-jwt-validation-purposes")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap")

from app.trading.briefing_advice import (
    EVENT_INSIDER_BUY,
    EVENT_INSIDER_SELL,
    EVENT_SOFT_STOP,
    advice_lines,
    load_investment_rules,
)
from app.trading.insider_edgar import parse_form4_xml
from app.trading.market_context import format_insider_report, format_soft_stop_report
from tests.test_insider_gate import FORM4

RULES = {
    "avoid_tickers": ["OGN"],
    "volatile_tickers": ["NVDA", "SNDK"],
    "stable_tickers": ["AAPL"],
    "watchlist_tier_s": ["TSM", "MSFT"],
    "watchlist_tier_a": ["PLTR"],
    "watchlist_tier_b": ["AMD"],
    "swing_target1_pct": 7.0,
    "swing_target2_pct": 12.0,
    "swing_stop_loss_pct": 5.0,
    "swing_max_concurrent_trades": 2,
    "swing_risk_per_trade_pct": 1.0,
    "reentry_cooloff_volatile_days": 2,
    "stable_bep_trigger_pct": 2.0,
    "sndk_strike3_ban_days": 5,
    "rules_text": ["Never chase — wait for entry, not momentum"],
}

SNAP_DUMP = {
    "vol_ratio": 2.4,
    "price_up": False,
    "leaving": True,
    "sector": "Technology",
    "sector_etf": "XLK",
    "sector_vol_ratio": 1.1,
    "sector_price_up": False,
}
SNAP_LIGHT = {
    "vol_ratio": 0.4,
    "price_up": False,
    "leaving": False,
    "sector": "Technology",
    "sector_etf": "XLK",
    "sector_vol_ratio": 0.8,
    "sector_price_up": False,
}
BEAR = [{"title": "cut", "score": -3, "label": "BEAR", "severity": "med", "source": "yahoo", "reasoning": "x"}]
BULL = [{"title": "beat", "score": 3, "label": "BULL", "severity": "med", "source": "yahoo", "reasoning": "x"}]


def test_load_real_rules_file():
    rules = load_investment_rules()
    assert "AAPL" in {t.upper() for t in rules.get("stable_tickers", [])}
    assert "OGN" in {t.upper() for t in rules.get("avoid_tickers", [])}
    assert "TSM" in {t.upper() for t in rules.get("watchlist_tier_s", [])}


def test_buy_watchlist_s_does_not_chase():
    lines = advice_lines(
        "TSM",
        EVENT_INSIDER_BUY,
        held=False,
        sector_pct=0.20,
        sector_cap=0.30,
        ticker_sector="Technology",
        snap=SNAP_LIGHT,
        news=BULL,
        rules=RULES,
    )
    blob = " ".join(lines)
    assert "Do not chase" in blob
    assert "tier S" in blob
    assert "10% room" in blob
    assert "FOMO" in blob


def test_buy_unknown_name_is_research_only():
    lines = advice_lines("XYZ", EVENT_INSIDER_BUY, held=False, rules=RULES)
    blob = " ".join(lines)
    assert "Not on S/A/B" in blob


def test_buy_held_no_average_down():
    lines = advice_lines("AAPL", EVENT_INSIDER_BUY, held=True, rules=RULES)
    blob = " ".join(lines)
    assert "Already in the book" in blob
    assert "No averaging down" in blob
    assert "STABLE" in blob


def test_buy_volatile_and_distribution():
    lines = advice_lines(
        "NVDA",
        EVENT_INSIDER_BUY,
        held=False,
        snap=SNAP_DUMP,
        news=BEAR,
        rules=RULES,
        cluster_count=3,
    )
    blob = " ".join(lines)
    assert "VOLATILE" in blob
    assert "LEAVING" in blob
    assert "Cluster 3" in blob
    assert "BEAR" in blob


def test_buy_sector_at_cap_blocks_add():
    lines = advice_lines(
        "TSM",
        EVENT_INSIDER_BUY,
        sector_pct=0.32,
        sector_cap=0.30,
        ticker_sector="Technology",
        rules=RULES,
    )
    assert any("no add" in x.lower() for x in lines)


def test_sell_held_respect_and_no_heroics():
    lines = advice_lines(
        "AAPL",
        EVENT_INSIDER_SELL,
        held=True,
        snap=SNAP_DUMP,
        news=BULL,
        rules=RULES,
    )
    blob = " ".join(lines)
    assert "respect it" in blob
    assert "Do not average down" in blob
    assert "LEAVING" in blob
    assert "Bull headlines" in blob


def test_soft_stop_dump_vs_shakeout():
    dump = advice_lines("AAPL", EVENT_SOFT_STOP, held=True, snap=SNAP_DUMP, stage="intraday", rules=RULES)
    light = advice_lines("AAPL", EVENT_SOFT_STOP, held=True, snap=SNAP_LIGHT, stage="intraday", rules=RULES)
    eod = advice_lines("NVDA", EVENT_SOFT_STOP, held=True, snap=SNAP_DUMP, stage="eod", rules=RULES)
    assert any("breakdown" in x.lower() or "LEAVING" in x for x in dump)
    assert any("shakeout" in x.lower() for x in light)
    assert any("tomorrow" in x.lower() for x in eod)
    assert any("no same-day re-entry" in x.lower() for x in eod)


def test_telegram_bodies_include_advice_section():
    filing = parse_form4_xml(FORM4)[0]
    buy = format_insider_report(
        filing, ["officer buy"], SNAP_DUMP, BEAR,
        sector_pct=0.20, sector_cap=0.30, ticker_sector="Technology",
        notional=300000, held=False, rules=RULES,
    )
    assert "Advice" in buy
    assert "Do not chase" in buy
    sell_filing = dict(filing)
    sell_filing["transaction_code"] = "S"
    sell = format_insider_report(
        sell_filing, ["held sell"], SNAP_DUMP, BULL,
        held=True, rules=RULES,
    )
    assert "respect it" in sell
    stop = format_soft_stop_report("AAPL", 140.12, 150.0, "intraday", SNAP_DUMP, BEAR, rules=RULES)
    assert "Advice" in stop
    assert "Do not average down" in stop
