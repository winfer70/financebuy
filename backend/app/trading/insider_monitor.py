"""insider_monitor.py — Poll EDGAR Form 4, gate, Telegram via notify_soft_stop.

Cron on trading-worker (job_timeout 300). Skips the cycle when SEC_USER_AGENT
is unset — SEC requires a contact email in the User-Agent.
"""
from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional, Protocol

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import InsiderFiling, Portfolio, PortfolioPosition, RuleAlert
from .briefing_advice import load_investment_rules
from .heartbeat import write_worker_heartbeat
from .insider_edgar import FORM4_ATOM_URL, parse_atom_accessions, parse_form4_xml, xml_doc_url_from_index_html
from .insider_gate import BookSnapshot, GateResult, Integrity, evaluate_filing, sector_exposure
from .market_context import fetch_ticker_news, fetch_volume_snapshot, format_insider_report
from .notifications import notify_soft_stop

logger = structlog.get_logger("insider_monitor")

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@db:5432/tickerTap",
)
_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
_MAX_NEW_PER_CYCLE = 10
_REQUEST_PAUSE_S = 0.25

_engine = create_async_engine(_DATABASE_URL, echo=False, pool_size=3, max_overflow=1, pool_pre_ping=True)
_SessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


class EdgarFetcher:
    def __init__(self, user_agent: str):
        self.user_agent = user_agent

    async def get(self, url: str) -> str:
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.text


class FilingStore(Protocol):
    async def seen(self, accession: str) -> bool: ...
    async def add_rows(self, rows: list[dict]) -> None: ...
    async def cluster_buyers(self, ticker: str, since: date) -> int: ...
    async def already_notified(self, accession: str) -> bool: ...
    async def mark_notified(self, accession: str, when: datetime) -> None: ...
    async def add_rule_alert(self, user_id, gate: GateResult, filing: dict, body: str) -> None: ...


class MemoryFilingStore:
    """In-memory store for unit tests — no SQLAlchemy."""

    def __init__(self):
        self.rows: list[dict] = []
        self.alerts: list[dict] = []

    async def seen(self, accession: str) -> bool:
        return any(r.get("accession") == accession for r in self.rows)

    async def add_rows(self, rows: list[dict]) -> None:
        self.rows.extend(rows)

    async def cluster_buyers(self, ticker: str, since: date) -> int:
        owners = set()
        for r in self.rows:
            if (r.get("ticker") or "").upper() != ticker.upper():
                continue
            if (r.get("transaction_code") or "").upper() != "P":
                continue
            d = _txn_date(r)
            if d is not None and d < since:
                continue
            owners.add(r.get("owner_cik"))
        return len(owners)

    async def already_notified(self, accession: str) -> bool:
        return any(r.get("accession") == accession and r.get("notified_at") for r in self.rows)

    async def mark_notified(self, accession: str, when: datetime) -> None:
        for r in self.rows:
            if r.get("accession") == accession:
                r["notified_at"] = when

    async def add_rule_alert(self, user_id, gate: GateResult, filing: dict, body: str) -> None:
        self.alerts.append(
            {"user_id": user_id, "event": gate.event_type, "title": filing.get("ticker"), "body": body}
        )


class SqlFilingStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def seen(self, accession: str) -> bool:
        res = await self.session.execute(
            select(InsiderFiling.filing_id).where(InsiderFiling.accession == accession).limit(1)
        )
        return res.scalar_one_or_none() is not None

    async def add_rows(self, rows: list[dict]) -> None:
        for i, d in enumerate(rows):
            shares = Decimal(str(d.get("shares") or 0))
            price = Decimal(str(d.get("price") or 0))
            self.session.add(
                InsiderFiling(
                    accession=d.get("accession") or "",
                    txn_index=i,
                    ticker=(d.get("ticker") or "").upper(),
                    issuer_cik=(d.get("issuer_cik") or "")[:10] or None,
                    owner_name=(d.get("owner_name") or "")[:256] or None,
                    owner_cik=(d.get("owner_cik") or "")[:10] or None,
                    is_director=bool(d.get("is_director")),
                    is_officer=bool(d.get("is_officer")),
                    is_ten_percent=bool(d.get("is_ten_percent")),
                    officer_title=(d.get("officer_title") or "")[:128] or None,
                    transaction_code=(d.get("transaction_code") or "")[:4],
                    acquired_disposed=(d.get("acquired_disposed") or "")[:1] or None,
                    shares=shares,
                    price=price,
                    notional=shares * price,
                    transaction_date=_txn_date(d),
                    is_10b5_1=d.get("is_10b5_1"),
                    filing_url=d.get("filing_url") or None,
                )
            )
        await self.session.flush()

    async def cluster_buyers(self, ticker: str, since: date) -> int:
        res = await self.session.execute(
            select(func.count(func.distinct(InsiderFiling.owner_cik))).where(
                InsiderFiling.ticker == ticker.upper(),
                InsiderFiling.transaction_code == "P",
                InsiderFiling.transaction_date >= since,
            )
        )
        return int(res.scalar() or 0)

    async def already_notified(self, accession: str) -> bool:
        res = await self.session.execute(
            select(InsiderFiling.notified_at)
            .where(InsiderFiling.accession == accession, InsiderFiling.notified_at.is_not(None))
            .limit(1)
        )
        return res.scalar_one_or_none() is not None

    async def mark_notified(self, accession: str, when: datetime) -> None:
        await self.session.execute(
            update(InsiderFiling)
            .where(InsiderFiling.accession == accession)
            .values(notified_at=when)
        )

    async def add_rule_alert(self, user_id, gate: GateResult, filing: dict, body: str) -> None:
        if user_id is None:
            return
        ticker = (filing.get("ticker") or "").upper()
        title = f"{ticker} {gate.event_type} ${gate.notional:,.0f}"[:200]
        self.session.add(
            RuleAlert(
                user_id=user_id,
                rule_type=gate.event_type[:32],
                severity=gate.severity[:10],
                title=title,
                body=body[:4000] if body else None,
                triggered_value=gate.notional,
                state="active",
            )
        )


@dataclass
class CycleDeps:
    load_book: Callable
    fetch_integrity: Callable
    fetch_volume: Callable
    fetch_news: Callable
    notify: Callable
    user_id: object = None
    ticker_sectors: dict = field(default_factory=dict)
    pause_s: float = 0.0


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _txn_date(row: dict) -> Optional[date]:
    raw = (row.get("transaction_date") or "")[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_avoid_tickers() -> set:
    return {str(t).upper() for t in load_investment_rules().get("avoid_tickers", [])}


async def load_book(session: AsyncSession) -> tuple[BookSnapshot, object, dict]:
    """Open positions → GICS sector weights. user_id is any portfolio owner."""
    res = await session.execute(
        select(PortfolioPosition, Portfolio.user_id)
        .join(Portfolio, Portfolio.portfolio_id == PortfolioPosition.portfolio_id)
        .where(
            PortfolioPosition.closed_at.is_(None),
            PortfolioPosition.is_excluded.is_(False),
        )
    )
    rows = res.all()
    pos_dicts = []
    held = set()
    sectors: dict[str, str] = {}
    user_id = None
    for pos, uid in rows:
        user_id = user_id or uid
        ticker = (pos.ticker or "").upper()
        held.add(ticker)
        if pos.sector:
            sectors[ticker] = pos.sector
        if pos.t2_usd is not None:
            mv = Decimal(str(pos.t2_usd))
        else:
            mv = Decimal(str(pos.purchase_price or 0)) * Decimal(str(pos.quantity or 0))
        pos_dicts.append({"sector": pos.sector or "Unknown", "market_value": mv})
    total = sum((p["market_value"] for p in pos_dicts), Decimal("0"))
    book = BookSnapshot(
        total_value=total,
        sector_values=sector_exposure(pos_dicts, total),
        held_tickers=held,
        avoid_tickers=load_avoid_tickers(),
    )
    return book, user_id, sectors


def fetch_integrity_sync(ticker: str) -> Integrity:
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        de = info.get("debtToEquity")
        return Integrity(debt_to_equity=float(de) if de is not None else None)
    except Exception:
        return Integrity()


def new_accessions(entries: list[dict], seen: set, limit: int = _MAX_NEW_PER_CYCLE) -> list[dict]:
    out = []
    for e in entries:
        acc = e.get("accession") or ""
        if not acc or acc in seen:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


async def run_insider_cycle(
    fetcher: EdgarFetcher,
    store: FilingStore,
    deps: CycleDeps,
    *,
    now: Optional[datetime] = None,
    limit: int = _MAX_NEW_PER_CYCLE,
) -> dict:
    """Fetch atom → XML → gate → notify. All I/O injected via fetcher/store/deps."""
    now = now or datetime.now(timezone.utc)
    since = (now.date() - timedelta(days=30))
    stats = {"fetched": 0, "new": 0, "telegram": 0, "in_app": 0, "errors": 0}

    atom = await fetcher.get(FORM4_ATOM_URL)
    entries = parse_atom_accessions(atom)
    stats["fetched"] = len(entries)

    seen: set[str] = set()
    fresh = []
    for e in entries:
        acc = e.get("accession") or ""
        if not acc:
            continue
        if acc in seen:
            continue
        if await store.seen(acc):
            seen.add(acc)
            continue
        seen.add(acc)
        fresh.append(e)
        if len(fresh) >= limit:
            break
    stats["new"] = len(fresh)

    book: BookSnapshot = await _maybe_await(deps.load_book())

    for entry in fresh:
        if deps.pause_s:
            await asyncio.sleep(deps.pause_s)
        try:
            index_html = await fetcher.get(entry["index_url"])
            xml_url = xml_doc_url_from_index_html(index_html, entry["accession"], entry.get("index_url") or "")
            if not xml_url:
                logger.info("insider_no_xml", accession=entry["accession"])
                continue
            if deps.pause_s:
                await asyncio.sleep(deps.pause_s)
            xml_text = await fetcher.get(xml_url)
            rows = parse_form4_xml(xml_text, accession=entry["accession"], filing_url=xml_url)
            if not rows:
                continue
            await store.add_rows(rows)

            # One briefing per accession (first P/S row that the gate cares about).
            notified = await store.already_notified(entry["accession"])
            for row in rows:
                code = (row.get("transaction_code") or "").upper()
                if code not in ("P", "S"):
                    continue
                ticker = (row.get("ticker") or "").upper()
                sector = deps.ticker_sectors.get(ticker)
                cluster = 1
                if code == "P":
                    cluster = await store.cluster_buyers(ticker, since)
                integrity = await _maybe_await(deps.fetch_integrity(ticker))
                gate = evaluate_filing(
                    row,
                    book,
                    ticker_sector=sector,
                    cluster_count=cluster,
                    integrity=integrity,
                )
                body = ""
                if gate.worth_telegram or gate.in_app:
                    snap = await _maybe_await(deps.fetch_volume(ticker, sector))
                    news = await _maybe_await(deps.fetch_news(ticker))
                    body = format_insider_report(
                        row,
                        gate.reasons,
                        snap or {},
                        news or [],
                        cluster_count=gate.cluster_count,
                        sector_pct=gate.sector_pct,
                        sector_cap=float(book.sector_cap),
                        ticker_sector=sector,
                        notional=float(gate.notional),
                        held=ticker in book.held_tickers,
                    )
                if gate.in_app:
                    await store.add_rule_alert(deps.user_id, gate, row, body)
                    stats["in_app"] += 1
                if gate.worth_telegram and not notified:
                    title = f"{ticker} insider {code} ${float(gate.notional):,.0f}"
                    if gate.severity == "critical":
                        title = "CRITICAL " + title
                    prio = 5 if gate.severity == "critical" else 3
                    await deps.notify(
                        deps.user_id,
                        gate.event_type,
                        title[:200],
                        body,
                        prio,
                    )
                    await store.mark_notified(entry["accession"], now)
                    notified = True
                    stats["telegram"] += 1
        except Exception:
            stats["errors"] += 1
            logger.exception("insider_entry_failed", accession=entry.get("accession"))
    return stats


async def poll_insider_filings(ctx: dict) -> dict:
    """arq cron entrypoint. No-op without SEC_USER_AGENT."""
    ua = (os.getenv("SEC_USER_AGENT") or "").strip()
    if not ua:
        logger.info("insider_poll_skipped", reason="SEC_USER_AGENT unset")
        return {"skipped": True, "reason": "no_user_agent"}

    fetcher = EdgarFetcher(ua)
    async with _SessionLocal() as session:
        store = SqlFilingStore(session)
        book, user_id, sectors = await load_book(session)
        loop = asyncio.get_running_loop()

        def _integrity(ticker: str) -> Integrity:
            return fetch_integrity_sync(ticker)

        def _volume(ticker: str, sector=None):
            try:
                return fetch_volume_snapshot(ticker, sector)
            except Exception:
                return {
                    "vol_ratio": None,
                    "price_up": None,
                    "leaving": False,
                    "sector": sector,
                    "sector_etf": None,
                    "sector_vol_ratio": None,
                    "sector_price_up": None,
                }

        async def _news(ticker: str):
            try:
                return await fetch_ticker_news(session, ticker)
            except Exception:
                return []

        async def _notify(uid, event_type, title, body, prio):
            if uid is None:
                logger.warning("insider_notify_no_user", title=title)
                return
            await notify_soft_stop(
                db=session,
                user_id=uid,
                event_type=event_type,
                title=title,
                body=body,
                metadata={"source": "insider_monitor"},
                ntfy_priority=prio,
                send_in_app=True,
                send_telegram=True,
                send_ntfy=True,
            )

        deps = CycleDeps(
            load_book=lambda: book,
            fetch_integrity=lambda t: loop.run_in_executor(None, _integrity, t),
            fetch_volume=lambda t, s=None: loop.run_in_executor(None, _volume, t, s),
            fetch_news=_news,
            notify=_notify,
            user_id=user_id,
            ticker_sectors=sectors,
            pause_s=_REQUEST_PAUSE_S,
        )
        stats = await run_insider_cycle(fetcher, store, deps)
        await session.commit()
        await write_worker_heartbeat("trading-worker", _REDIS_URL, jobs_processed_delta=1, last_error="")
        logger.info("insider_poll_done", **stats)
        return stats
