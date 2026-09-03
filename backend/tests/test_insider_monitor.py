"""Insider poller cycle tests — EDGAR HTTP and SQL mocked."""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-jwt-validation-purposes")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/tickerTap")

import pytest

from app.trading.insider_gate import Integrity
from app.trading.insider_monitor import (
    CycleDeps,
    MemoryFilingStore,
    new_accessions,
    poll_insider_filings,
    run_insider_cycle,
)
from tests.test_insider_gate import ATOM, FORM4, INDEX_HTML, _book

SNAP = {
    "vol_ratio": 1.2,
    "price_up": True,
    "leaving": False,
    "sector": "Technology",
    "sector_etf": "XLK",
    "sector_vol_ratio": 0.9,
    "sector_price_up": True,
}
NEWS = [
    {
        "title": "iPhone demand holds",
        "score": 3,
        "label": "BULL",
        "severity": "med",
        "source": "yahoo",
        "reasoning": "unit growth",
    }
]


class MapFetcher:
    def __init__(self, mapping: dict):
        self.user_agent = "TickerTap tests@example.com"
        self.mapping = mapping
        self.urls = []

    async def get(self, url: str) -> str:
        self.urls.append(url)
        for needle, body in self.mapping.items():
            if needle in url:
                return body
        raise AssertionError(f"unexpected url {url}")


def _mapping(xml=FORM4, atom=ATOM, index=INDEX_HTML):
    return {
        "output=atom": atom,
        "index.htm": index,
        "wk-form4.xml": xml,
    }


def _deps(book=None, notifies=None, user_id=None):
    notifies = notifies if notifies is not None else []
    uid = user_id or uuid.uuid4()

    async def _notify(user, event, title, body, prio):
        notifies.append(
            {"user_id": user, "event": event, "title": title, "body": body, "prio": prio}
        )

    return CycleDeps(
        load_book=lambda: book or _book(),
        fetch_integrity=lambda _t: Integrity(),
        fetch_volume=lambda _t, _s=None: SNAP,
        fetch_news=lambda _t: NEWS,
        notify=_notify,
        user_id=uid,
        ticker_sectors={"AAPL": "Technology", "OGN": "Healthcare"},
        pause_s=0.0,
    ), notifies


@pytest.mark.asyncio
async def test_cycle_officer_buy_sends_telegram():
    store = MemoryFilingStore()
    deps, notifies = _deps()
    stats = await run_insider_cycle(
        MapFetcher(_mapping()),
        store,
        deps,
        now=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    assert stats["new"] == 1
    assert stats["telegram"] == 1
    assert stats["in_app"] == 1
    assert len(notifies) == 1
    assert notifies[0]["event"] == "insider_buy"
    assert "AAPL" in notifies[0]["title"]
    assert "concern" in notifies[0]["title"]
    assert "BULL" in notifies[0]["body"] or "iPhone" in notifies[0]["body"]
    assert "10b5-1" in notifies[0]["body"]
    assert "Your position:" in notifies[0]["body"]
    assert "XLK" in notifies[0]["body"] or "Volume" in notifies[0]["body"]
    assert store.rows[0]["accession"] == "0000320193-26-000123"
    assert store.rows[0]["notified_at"] is not None
    assert store.alerts[0]["event"] == "insider_buy"


@pytest.mark.asyncio
async def test_cycle_skip_known_accession():
    store = MemoryFilingStore()
    store.rows.append({"accession": "0000320193-26-000123", "ticker": "AAPL", "transaction_code": "P"})
    deps, notifies = _deps()
    stats = await run_insider_cycle(MapFetcher(_mapping()), store, deps)
    assert stats["new"] == 0
    assert notifies == []


@pytest.mark.asyncio
async def test_cycle_avoid_ticker_no_telegram():
    xml = FORM4.replace("AAPL", "OGN")
    store = MemoryFilingStore()
    deps, notifies = _deps()
    stats = await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)
    assert stats["telegram"] == 0
    assert stats["in_app"] == 1
    assert notifies == []
    assert store.alerts[0]["event"] == "insider_buy"


@pytest.mark.asyncio
async def test_cycle_held_sell_is_critical_telegram():
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    store = MemoryFilingStore()
    deps, notifies = _deps(book=_book(held_tickers={"AAPL"}))
    stats = await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)
    assert stats["telegram"] == 1
    assert notifies[0]["event"] == "insider_sell"
    assert "concern" in notifies[0]["title"]
    # discretionary (no 10b5) held sell → high priority
    assert notifies[0]["prio"] == 5
    assert "CRITICAL" in notifies[0]["title"] or "HIGH" in notifies[0]["title"] or "SELL" in notifies[0]["title"]


@pytest.mark.asyncio
async def test_cycle_does_not_renotify_same_accession():
    store = MemoryFilingStore()
    deps, notifies = _deps()
    fetcher = MapFetcher(_mapping())
    await run_insider_cycle(fetcher, store, deps)
    stats2 = await run_insider_cycle(fetcher, store, deps)
    assert stats2["new"] == 0
    assert len(notifies) == 1


@pytest.mark.asyncio
async def test_poll_skips_without_user_agent(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    result = await poll_insider_filings({})
    assert result["skipped"] is True
    assert result["reason"] == "no_user_agent"


def test_new_accessions_caps_and_skips_seen():
    entries = [
        {"accession": "a"},
        {"accession": "b"},
        {"accession": "c"},
        {"accession": "a"},
    ]
    got = new_accessions(entries, seen={"a"}, limit=1)
    assert [e["accession"] for e in got] == ["b"]


def test_worker_registers_insider_job():
    from app.trading.worker import WorkerSettings

    assert any(getattr(fn, "__name__", "") == "poll_insider_filings" for fn in WorkerSettings.functions)
    cron_fns = [c.coroutine.__name__ if hasattr(c, "coroutine") else str(c) for c in WorkerSettings.cron_jobs]
    assert "poll_insider_filings" in cron_fns


def test_news_worker_defaults_to_hermes_and_key_fallback():
    root = Path(__file__).resolve().parents[1].parent
    text = (root / "server-b-worker" / "worker.py").read_text(encoding="utf-8")
    assert 'os.getenv("OLLAMA_MODEL", "hermes3:8b")' in text
    assert 'os.getenv("TICKERTAP_INTERNAL_KEY") or os.getenv("INTERNAL_NEWS_KEY"' in text
    queue = (Path(__file__).resolve().parents[1].parent / "server-b-worker" / "article_queue.py").read_text(
        encoding="utf-8"
    )
    assert "NEWS_QUEUE_DIR" in queue


@pytest.mark.asyncio
async def test_all_new_features_together():
    """Soft-stop copy + Form 4 parse + gate + poller briefing share volume/news helpers."""
    from app.trading.insider_edgar import parse_form4_xml
    from app.trading.insider_gate import evaluate_filing
    from app.trading.market_context import format_insider_report, format_soft_stop_report

    filing = parse_form4_xml(FORM4)[0]
    book = _book()
    gate = evaluate_filing(filing, book, ticker_sector="Technology", cluster_count=1)
    assert gate.worth_telegram is True

    soft_body = format_soft_stop_report("AAPL", 140.12, 150.0, "intraday", SNAP, NEWS)
    assert "$140.12" in soft_body
    assert "iPhone demand" in soft_body

    insider_body = format_insider_report(
        filing,
        gate.reasons,
        SNAP,
        NEWS,
        cluster_count=gate.cluster_count,
        sector_pct=gate.sector_pct,
        sector_cap=float(book.sector_cap),
        ticker_sector="Technology",
        notional=float(gate.notional),
    )
    assert "COOK TIMOTHY" in insider_body or "CEO" in insider_body
    assert "10b5-1" in insider_body
    assert "XLK" in insider_body and "XLK" in soft_body
    assert "BULL" in insider_body and "BULL" in soft_body

    store = MemoryFilingStore()
    deps, notifies = _deps(book=book)
    stats = await run_insider_cycle(
        MapFetcher(_mapping()),
        store,
        deps,
        now=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )
    assert stats["telegram"] == 1
    assert stats["in_app"] == 1
    assert "BULL" in notifies[0]["body"]
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    store2 = MemoryFilingStore()
    deps2, sells = _deps(book=_book(held_tickers={"AAPL"}))
    sell_stats = await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store2, deps2)
    assert sell_stats["telegram"] == 1
    assert sells[0]["event"] == "insider_sell"
