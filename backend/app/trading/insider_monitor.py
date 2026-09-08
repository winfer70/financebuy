"""insider_monitor.py — Poll EDGAR Form 4, gate, Telegram via notify_soft_stop.

Cron on trading-worker (job_timeout 300). Skips the cycle when SEC_USER_AGENT
is unset — SEC requires a contact email in the User-Agent.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable, Optional, Protocol

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from ..models import InsiderFiling, Portfolio, PortfolioPosition, RuleAlert
from .briefing_advice import load_investment_rules
from .heartbeat import write_worker_heartbeat
from .insider_briefing import (
    ConsensusBrief,
    PositionBrief,
    summarize_owner_history,
)
from .insider_edgar import (
    FORM4_ATOM_URL,
    EdgarFetcher,
    parse_atom_accessions,
    parse_form4_xml,
    xml_doc_url_from_index_html,
)
from .finra_short_interest import get_latest_short_interest
from .form144_monitor import get_recent_144_notice
from .insider_gate import BookSnapshot, GateResult, Integrity, evaluate_filing, sector_exposure
from .insider_track_record import compute_track_record
from .market_context import (
    fetch_price_history_bars,
    fetch_ticker_news,
    fetch_volume_snapshot,
    format_insider_report,
    format_insider_title,
)
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


class FilingStore(Protocol):
    async def seen(self, accession: str) -> bool: ...
    async def add_rows(self, rows: list[dict]) -> None: ...
    async def cluster_owners(self, ticker: str, code: str, since: date) -> int: ...
    async def owner_history(
        self, owner_cik: str, ticker: str, code: str, since: date
    ) -> list[dict]: ...
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

    async def cluster_owners(self, ticker: str, code: str, since: date) -> int:
        owners = set()
        for r in self.rows:
            if (r.get("ticker") or "").upper() != ticker.upper():
                continue
            if (r.get("transaction_code") or "").upper() != code.upper():
                continue
            d = _txn_date(r)
            if d is not None and d < since:
                continue
            owners.add(r.get("owner_cik"))
        return len(owners)

    async def cluster_buyers(self, ticker: str, since: date) -> int:
        return await self.cluster_owners(ticker, "P", since)

    async def owner_history(self, owner_cik: str, ticker: str, code: str, since: date) -> list[dict]:
        out = []
        for r in self.rows:
            if (r.get("owner_cik") or "") != (owner_cik or ""):
                continue
            if (r.get("ticker") or "").upper() != ticker.upper():
                continue
            if (r.get("transaction_code") or "").upper() != code.upper():
                continue
            d = _txn_date(r)
            if d is not None and d < since:
                continue
            out.append(r)
        return out

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
            shares_after = d.get("shares_after")
            stake = d.get("stake_pct")
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
                    shares_after=Decimal(str(shares_after)) if shares_after is not None else None,
                    stake_pct=Decimal(str(stake)) if stake is not None else None,
                    transaction_date=_txn_date(d),
                    is_10b5_1=d.get("is_10b5_1"),
                    filing_url=d.get("filing_url") or None,
                )
            )
        await self.session.flush()

    async def cluster_owners(self, ticker: str, code: str, since: date) -> int:
        res = await self.session.execute(
            select(func.count(func.distinct(InsiderFiling.owner_cik))).where(
                InsiderFiling.ticker == ticker.upper(),
                InsiderFiling.transaction_code == code.upper(),
                InsiderFiling.transaction_date >= since,
            )
        )
        return int(res.scalar() or 0)

    async def cluster_buyers(self, ticker: str, since: date) -> int:
        return await self.cluster_owners(ticker, "P", since)

    async def owner_history(self, owner_cik: str, ticker: str, code: str, since: date) -> list[dict]:
        if not owner_cik:
            return []
        res = await self.session.execute(
            select(InsiderFiling)
            .where(
                InsiderFiling.owner_cik == owner_cik[:10],
                InsiderFiling.ticker == ticker.upper(),
                InsiderFiling.transaction_code == code.upper(),
                InsiderFiling.transaction_date >= since,
            )
            .order_by(InsiderFiling.transaction_date.asc())
        )
        out = []
        for row in res.scalars().all():
            out.append(
                {
                    "accession": row.accession,
                    "shares": float(row.shares or 0),
                    "transaction_date": row.transaction_date,
                    "transaction_code": row.transaction_code,
                    "owner_cik": row.owner_cik,
                    "ticker": row.ticker,
                }
            )
        return out

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
    fetch_consensus: Optional[Callable] = None
    # (combined_owner_history_rows, ticker) -> TrackRecord | None — appended
    # to the Telegram body as "Track record: <label>" when present. Optional
    # so existing tests/callers that don't set it are unaffected.
    fetch_track_record: Optional[Callable] = None
    # (owner_cik, ticker) -> Form144Notice | None — a sell that was
    # pre-announced via Form 144 gets a note instead of reading as a
    # surprise dump. Optional so existing tests/callers are unaffected.
    fetch_144_notice: Optional[Callable] = None
    # (ticker) -> ShortInterestSnapshot | None — squeeze/crowding context
    # from FINRA's biweekly data. Optional so existing tests/callers are
    # unaffected.
    fetch_short_interest: Optional[Callable] = None
    # New, multi-user path: returns dict[user_id, BookSnapshot], one book per
    # user who has open positions. When set, run_insider_cycle evaluates and
    # notifies each *holder* of the filed ticker separately (their own
    # sector_pct/held/position, hence their own personalized advice), instead
    # of the single global book+user_id below. Optional and defaults to None
    # so existing single-user callers/tests (load_book + user_id) are
    # unaffected — they synthesize a one-entry books dict internally.
    load_books: Optional[Callable] = None
    # Who gets a BUY-type "new idea" alert on a ticker nobody holds yet — that
    # kind of alert is inherently about *someone's* personal watchlist/rules
    # config (investment_rules.json), not a specific holding, so it can't be
    # fanned out to every user. Defaults to `user_id` for backward compat.
    primary_user_id: object = None


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _txn_date(row: dict) -> Optional[date]:
    raw = row.get("transaction_date")
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    raw = (str(raw) if raw is not None else "")[:10]
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_avoid_tickers() -> set:
    return {str(t).upper() for t in load_investment_rules().get("avoid_tickers", [])}


async def load_books(session: AsyncSession) -> tuple[dict, dict]:
    """Open positions → one BookSnapshot per user who holds any, keyed by
    user_id, plus a shared ticker->sector map (issuer-level metadata, not
    user-specific, so it's fine to pool across everyone's positions).

    Replaces the old single-aggregate load_book(), which combined every
    user's positions into one BookSnapshot and picked "whichever user_id
    was encountered first" for every notification — meaning a second user
    (e.g. a friend with their own linked Telegram chat) never got their own
    personalized gate/advice, and could even have their position silently
    overwritten in the shared `positions` dict if they and another user both
    held the same ticker (dict keys are ticker, not (user, ticker)).
    """
    res = await session.execute(
        select(PortfolioPosition, Portfolio.user_id)
        .join(Portfolio, Portfolio.portfolio_id == PortfolioPosition.portfolio_id)
        .where(
            PortfolioPosition.closed_at.is_(None),
            PortfolioPosition.is_excluded.is_(False),
        )
    )
    rows = res.all()
    by_user: dict = {}
    sectors: dict[str, str] = {}
    for pos, uid in rows:
        by_user.setdefault(uid, []).append(pos)
        ticker = (pos.ticker or "").upper()
        if pos.sector:
            sectors[ticker] = pos.sector

    avoid = load_avoid_tickers()
    books: dict = {}
    for uid, user_positions in by_user.items():
        pos_dicts = []
        held = set()
        positions: dict = {}
        for pos in user_positions:
            ticker = (pos.ticker or "").upper()
            held.add(ticker)
            if pos.t2_usd is not None:
                mv = Decimal(str(pos.t2_usd))
            else:
                mv = Decimal(str(pos.purchase_price or 0)) * Decimal(str(pos.quantity or 0))
            pos_dicts.append({"sector": pos.sector or "Unknown", "market_value": mv})
            positions[ticker] = {
                "quantity": float(pos.quantity or 0),
                "purchase_price": float(pos.purchase_price or 0),
                "hard_stop": float(pos.hard_stop_loss) if pos.hard_stop_loss is not None else None,
                "soft_stop": float(pos.soft_stop_loss) if pos.soft_stop_loss is not None else None,
                "date_entered": pos.date_entered,
            }
        total = sum((p["market_value"] for p in pos_dicts), Decimal("0"))
        books[uid] = BookSnapshot(
            total_value=total,
            sector_values=sector_exposure(pos_dicts, total),
            held_tickers=held,
            avoid_tickers=avoid,
            positions=positions,
        )
    return books, sectors


def fetch_integrity_sync(ticker: str) -> Integrity:
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        de = info.get("debtToEquity")
        return Integrity(debt_to_equity=float(de) if de is not None else None)
    except Exception:
        return Integrity()


def fetch_consensus_sync(ticker: str, last_price: Optional[float] = None) -> Optional[ConsensusBrief]:
    """Best-effort analyst snapshot from yfinance — never raises."""
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
        target = info.get("targetMedianPrice") or info.get("targetMeanPrice")
        n = info.get("numberOfAnalystOpinions")
        # recommendationKey: strong_buy / buy / hold / sell / strong_sell
        key = (info.get("recommendationKey") or "").replace("_", " ").title()
        upside = None
        if target is not None and last_price:
            upside = (float(target) / float(last_price) - 1.0) * 100.0
        elif target is not None and info.get("currentPrice"):
            upside = (float(target) / float(info["currentPrice"]) - 1.0) * 100.0
        if not key and target is None:
            return None
        return ConsensusBrief(
            rating=key or None,
            n_analysts=int(n) if n else None,
            n_buy=None,
            target=float(target) if target is not None else None,
            upside_pct=upside,
        )
    except Exception:
        return None


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


def _format_144_note(notice) -> str:
    """Turns a matched Form144Notice into the 'pre-announced' line appended
    to a sell alert's body — a sale that was already on file via Form 144
    reads very differently than one with no prior notice at all."""
    parts = ["Pre-announced via Form 144"]
    if notice.notice_date:
        parts.append(f"on {notice.notice_date.isoformat()}")
    if notice.shares:
        parts.append(f"for {float(notice.shares):,.0f} sh")
    if notice.aggregate_value:
        parts.append(f"(~${float(notice.aggregate_value):,.0f})")
    if notice.approx_sale_date:
        parts.append(f"— proposed sale date {notice.approx_sale_date.isoformat()}")
    parts.append("— this Form 4 matches a notice already on file, not a surprise.")
    return " ".join(parts)


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
    since_30 = now.date() - timedelta(days=30)
    since_365 = now.date() - timedelta(days=365)
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

    if deps.load_books is not None:
        books: dict = await _maybe_await(deps.load_books())
    else:
        # Backward-compat single-book path (existing tests / any caller that
        # hasn't moved to load_books yet).
        single_book: BookSnapshot = await _maybe_await(deps.load_book())
        books = {deps.user_id: single_book} if deps.user_id is not None else {}
    primary_uid = deps.primary_user_id if deps.primary_user_id is not None else deps.user_id
    empty_book = BookSnapshot(
        total_value=Decimal("0"), sector_values={}, held_tickers=set(), avoid_tickers=load_avoid_tickers()
    )

    for entry in fresh:
        if deps.pause_s:
            await asyncio.sleep(deps.pause_s)
        try:
            index_html = await fetcher.get(entry["index_url"])
            xml_url = xml_doc_url_from_index_html(
                index_html, entry["accession"], entry.get("index_url") or ""
            )
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

            # Telegram is sent at most once per (accession, user) — scoped to
            # this accession's row loop, since one Form 4 filing can list
            # several non-derivative transaction lines. Cross-cycle
            # dedup doesn't need a separate check: an accession only ever
            # reaches this loop once, on the cycle it's first discovered
            # (store.seen() gates it out of `fresh` on every later cycle).
            accession_notified: set = set()
            for row in rows:
                code = (row.get("transaction_code") or "").upper()
                if code not in ("P", "S"):
                    continue
                ticker = (row.get("ticker") or "").upper()
                sector = deps.ticker_sectors.get(ticker)
                cluster = await store.cluster_owners(ticker, code, since_30)
                hist = await store.owner_history(
                    row.get("owner_cik") or "", ticker, code, since_365
                )
                pattern = summarize_owner_history(
                    hist,
                    current_shares=float(row.get("shares") or 0),
                    current_date=_txn_date(row),
                )
                integrity = await _maybe_await(deps.fetch_integrity(ticker))

                # Evaluate against every user who actually holds this ticker
                # — each gets their own sector_pct/held/position, hence their
                # own personalized advice and their own Telegram chat. A BUY
                # ("new idea") filing on a ticker nobody holds yet still goes
                # to the primary/owner user, since that's inherently about
                # their personal watchlist/rules config, not a holding.
                targets = {uid: b for uid, b in books.items() if ticker in b.held_tickers}
                if code == "P" and primary_uid is not None and primary_uid not in targets:
                    targets[primary_uid] = books.get(primary_uid, empty_book)

                # Shared across targets — these don't depend on whose book
                # we're evaluating against, only on the filing/ticker itself.
                snap = None
                news: list = []
                news_status = "ok"
                consensus = None
                track_record_label = None
                notice_144_label = None
                short_interest = None
                fetched_shared = False

                for uid, book in targets.items():
                    gate = evaluate_filing(
                        row,
                        book,
                        ticker_sector=sector,
                        cluster_count=cluster,
                        integrity=integrity,
                    )
                    body = ""
                    title = ""
                    if gate.worth_telegram or gate.in_app:
                        if not fetched_shared:
                            snap = await _maybe_await(deps.fetch_volume(ticker, sector))
                            try:
                                news = await _maybe_await(deps.fetch_news(ticker))
                                if news is None:
                                    news, news_status = [], "error"
                                elif not news:
                                    news_status = "empty"
                            except Exception:
                                news, news_status = [], "error"
                            if deps.fetch_consensus:
                                consensus = await _maybe_await(
                                    deps.fetch_consensus(ticker, float(row.get("price") or 0) or None)
                                )
                            if deps.fetch_track_record:
                                buy_hist = await store.owner_history(
                                    row.get("owner_cik") or "", ticker, "P", since_365
                                )
                                sell_hist = await store.owner_history(
                                    row.get("owner_cik") or "", ticker, "S", since_365
                                )
                                tr = await _maybe_await(
                                    deps.fetch_track_record(buy_hist + sell_hist, ticker)
                                )
                                if tr and tr.label:
                                    track_record_label = tr.label
                            if code == "S" and deps.fetch_144_notice:
                                notice = await _maybe_await(
                                    deps.fetch_144_notice(row.get("owner_cik") or "", ticker)
                                )
                                if notice is not None:
                                    notice_144_label = _format_144_note(notice)
                            if deps.fetch_short_interest:
                                short_interest = await _maybe_await(deps.fetch_short_interest(ticker))
                            fetched_shared = True
                        pos_raw = (book.positions or {}).get(ticker)
                        position = PositionBrief(**pos_raw) if pos_raw else None
                        title = format_insider_title(
                            row,
                            notional=float(gate.notional),
                            cluster_count=cluster,
                            pattern=pattern,
                        )
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
                            pattern=pattern,
                            position=position,
                            consensus=consensus,
                            short_interest=short_interest,
                            news_status=news_status,
                        )
                        if track_record_label:
                            body = f"{body}\n\nTrack record: {track_record_label}"
                        if notice_144_label:
                            body = f"{body}\n\n{notice_144_label}"
                    if gate.in_app:
                        await store.add_rule_alert(uid, gate, row, body)
                        stats["in_app"] += 1
                    if gate.worth_telegram and uid not in accession_notified:
                        prio = 5 if gate.severity == "critical" else 4 if gate.severity == "warning" else 3
                        await deps.notify(
                            uid,
                            gate.event_type,
                            (title or f"{ticker} insider {code}")[:200],
                            body,
                            prio,
                        )
                        accession_notified.add(uid)
                        stats["telegram"] += 1
            if accession_notified:
                await store.mark_notified(entry["accession"], now)
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
        books, sectors = await load_books(session)
        primary_user_id = None
        raw_primary = (os.getenv("BOT_USER_ID") or "").strip()
        if raw_primary:
            try:
                primary_user_id = uuid.UUID(raw_primary)
            except ValueError:
                logger.warning("insider_bad_bot_user_id", value=raw_primary)
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
            return await fetch_ticker_news(session, ticker)

        def _consensus(ticker: str, price=None):
            return fetch_consensus_sync(ticker, price)

        def _track_record(rows: list[dict], ticker: str):
            try:
                bars = fetch_price_history_bars(ticker, period="2y")
            except Exception:
                return None
            return compute_track_record(rows, bars)

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
            load_book=None,
            load_books=lambda: books,
            fetch_integrity=lambda t: loop.run_in_executor(None, _integrity, t),
            fetch_volume=lambda t, s=None: loop.run_in_executor(None, _volume, t, s),
            fetch_news=_news,
            fetch_consensus=lambda t, p=None: loop.run_in_executor(None, _consensus, t, p),
            fetch_track_record=lambda rows, t: loop.run_in_executor(None, _track_record, rows, t),
            fetch_144_notice=lambda cik, t: get_recent_144_notice(session, cik, t),
            fetch_short_interest=lambda t: get_latest_short_interest(session, t),
            notify=_notify,
            primary_user_id=primary_user_id,
            ticker_sectors=sectors,
            pause_s=_REQUEST_PAUSE_S,
        )
        stats = await run_insider_cycle(fetcher, store, deps)
        await session.commit()
        await write_worker_heartbeat(
            "trading-worker", _REDIS_URL, jobs_processed_delta=1, last_error=""
        )
        logger.info("insider_poll_done", **stats)
        return stats
