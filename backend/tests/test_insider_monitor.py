"""Insider poller cycle tests — EDGAR HTTP and SQL mocked."""
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
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


def _deps_multi(
    books: dict, primary_user_id=None, notifies=None, fetch_track_record=None, fetch_144_notice=None
):
    """Multi-user CycleDeps — exercises the new load_books path directly,
    as production code (poll_insider_filings) now does."""
    notifies = notifies if notifies is not None else []

    async def _notify(user, event, title, body, prio):
        notifies.append(
            {"user_id": user, "event": event, "title": title, "body": body, "prio": prio}
        )

    return CycleDeps(
        load_book=None,
        load_books=lambda: books,
        fetch_integrity=lambda _t: Integrity(),
        fetch_volume=lambda _t, _s=None: SNAP,
        fetch_news=lambda _t: NEWS,
        notify=_notify,
        primary_user_id=primary_user_id,
        fetch_track_record=fetch_track_record,
        fetch_144_notice=fetch_144_notice,
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
async def test_multi_user_sell_notifies_only_the_holder():
    """Regression: load_book() used to pick 'whichever user was iterated
    first' for every notification, so a sell on a ticker only user B holds
    could end up attributed to user A. With load_books, only the actual
    holder is evaluated/notified."""
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    holder, non_holder = uuid.uuid4(), uuid.uuid4()
    books = {
        holder: _book(held_tickers={"AAPL"}),
        non_holder: _book(held_tickers={"MSFT"}),
    }
    store = MemoryFilingStore()
    deps, notifies = _deps_multi(books)
    stats = await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)

    assert stats["telegram"] == 1
    assert len(notifies) == 1
    assert notifies[0]["user_id"] == holder
    assert notifies[0]["event"] == "insider_sell"


@pytest.mark.asyncio
async def test_multi_user_both_holders_get_own_personalized_notification():
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    books = {
        user_a: _book(held_tickers={"AAPL"}, sector_values={"Technology": Decimal("100000")}),
        user_b: _book(held_tickers={"AAPL"}, sector_values={"Technology": Decimal("900000")}),
    }
    store = MemoryFilingStore()
    deps, notifies = _deps_multi(books)
    stats = await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)

    assert stats["telegram"] == 2
    notified_users = {n["user_id"] for n in notifies}
    assert notified_users == {user_a, user_b}
    # Both got an in-app RuleAlert too, one each.
    assert len(store.alerts) == 2
    assert {a["user_id"] for a in store.alerts} == {user_a, user_b}


@pytest.mark.asyncio
async def test_multi_user_buy_on_unheld_ticker_goes_to_primary_only():
    """A BUY 'new idea' filing on a ticker nobody holds is inherently about
    the primary/owner's personal watchlist config — it must not fan out to
    every user, since a friend has no reason to see the owner's research."""
    primary, other = uuid.uuid4(), uuid.uuid4()
    books = {other: _book(held_tickers={"MSFT"})}  # `other` holds something, just not AAPL
    store = MemoryFilingStore()
    deps, notifies = _deps_multi(books, primary_user_id=primary)
    stats = await run_insider_cycle(
        MapFetcher(_mapping()),
        store,
        deps,
        now=datetime(2026, 9, 2, tzinfo=timezone.utc),
    )

    assert stats["telegram"] == 1
    assert notifies[0]["user_id"] == primary


@pytest.mark.asyncio
async def test_multi_user_accession_marked_notified_once_both_users_done():
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    books = {
        user_a: _book(held_tickers={"AAPL"}),
        user_b: _book(held_tickers={"AAPL"}),
    }
    store = MemoryFilingStore()
    fetcher = MapFetcher(_mapping(xml=xml))
    deps, notifies = _deps_multi(books)
    await run_insider_cycle(fetcher, store, deps)
    assert len(notifies) == 2
    assert store.rows[0]["notified_at"] is not None

    # A second cycle must not re-notify either user for the same accession.
    stats2 = await run_insider_cycle(fetcher, store, deps)
    assert stats2["new"] == 0
    assert len(notifies) == 2


@pytest.mark.asyncio
async def test_track_record_label_appended_to_telegram_body_when_available():
    """Regression: the track-record feature was wired into the web API/UI
    but never into the actual Telegram message — this is the missing piece
    a real alert (SHMD, 2026-09-08) was found to lack."""
    from app.trading.insider_track_record import TrackRecord

    async def _fetch_track_record(rows, ticker):
        return TrackRecord(
            sample_size=3, evaluated=2, win_rate=1.0, avg_aligned_return_pct=9.5,
            horizon_days=30, label="Favorable track record: 2/2 trades (100%) ...",
            basis="2 of 3 open-market P/S trades had 30-day forward price data.",
        )

    store = MemoryFilingStore()
    deps, notifies = _deps_multi({}, primary_user_id=uuid.uuid4(), fetch_track_record=_fetch_track_record)
    await run_insider_cycle(
        MapFetcher(_mapping()), store, deps, now=datetime(2026, 9, 2, tzinfo=timezone.utc)
    )

    assert len(notifies) == 1
    assert "Track record: Favorable track record" in notifies[0]["body"]


@pytest.mark.asyncio
async def test_no_track_record_section_when_fetch_track_record_unset():
    """Existing/default behavior — no fetch_track_record configured at all
    (matches the pre-2026-09-08 deployed state) must not error or add text."""
    store = MemoryFilingStore()
    deps, notifies = _deps_multi({}, primary_user_id=uuid.uuid4())
    await run_insider_cycle(
        MapFetcher(_mapping()), store, deps, now=datetime(2026, 9, 2, tzinfo=timezone.utc)
    )
    assert len(notifies) == 1
    assert "Track record:" not in notifies[0]["body"]


@pytest.mark.asyncio
async def test_144_notice_note_appended_to_sell_telegram_body():
    """A sell that was pre-announced via Form 144 should read differently
    from a surprise dump — see form144_monitor.get_recent_144_notice."""
    from datetime import date as _date

    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")

    class _FakeNotice:
        shares = Decimal("177701")
        aggregate_value = Decimal("18134387")
        approx_sale_date = _date(2026, 9, 8)
        notice_date = _date(2026, 9, 1)

    async def _fetch_144(owner_cik, ticker):
        return _FakeNotice()

    store = MemoryFilingStore()
    holder = uuid.uuid4()
    deps, notifies = _deps_multi({holder: _book(held_tickers={"AAPL"})}, fetch_144_notice=_fetch_144)
    await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)

    assert len(notifies) == 1
    body = notifies[0]["body"]
    assert "Pre-announced via Form 144" in body
    assert "2026-09-01" in body
    assert "177,701 sh" in body
    assert "2026-09-08" in body  # proposed sale date


@pytest.mark.asyncio
async def test_no_144_note_when_fetch_144_notice_unset():
    """Default/pre-feature behavior — no fetch_144_notice configured must
    not error or add text."""
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")
    store = MemoryFilingStore()
    deps, notifies = _deps_multi({uuid.uuid4(): _book(held_tickers={"AAPL"})})
    await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)
    assert len(notifies) == 1
    assert "Pre-announced via Form 144" not in notifies[0]["body"]


@pytest.mark.asyncio
async def test_no_144_lookup_attempted_for_buy_filings():
    """fetch_144_notice is a sell-side concept (144s only cover proposed
    *sales*) — a buy filing must never even call the correlation lookup."""
    called = False

    async def _fetch_144(owner_cik, ticker):
        nonlocal called
        called = True
        return None

    store = MemoryFilingStore()
    deps, notifies = _deps_multi({}, primary_user_id=uuid.uuid4(), fetch_144_notice=_fetch_144)
    await run_insider_cycle(MapFetcher(_mapping()), store, deps)  # default FORM4 is a "P" buy
    assert len(notifies) == 1
    assert called is False


@pytest.mark.asyncio
async def test_no_144_note_when_no_matching_notice_on_file():
    xml = FORM4.replace("<transactionCode>P</transactionCode>", "<transactionCode>S</transactionCode>")

    async def _fetch_144(owner_cik, ticker):
        return None

    store = MemoryFilingStore()
    deps, notifies = _deps_multi({uuid.uuid4(): _book(held_tickers={"AAPL"})}, fetch_144_notice=_fetch_144)
    await run_insider_cycle(MapFetcher(_mapping(xml=xml)), store, deps)
    assert len(notifies) == 1
    assert "Pre-announced via Form 144" not in notifies[0]["body"]


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


def test_worker_registers_form144_job():
    from app.trading.worker import WorkerSettings

    assert any(getattr(fn, "__name__", "") == "poll_form144_filings" for fn in WorkerSettings.functions)
    cron_fns = [c.coroutine.__name__ if hasattr(c, "coroutine") else str(c) for c in WorkerSettings.cron_jobs]
    assert "poll_form144_filings" in cron_fns


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
