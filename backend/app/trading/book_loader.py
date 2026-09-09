"""book_loader.py — Build per-user BookSnapshots (portfolio + watchlist).

Extracted from insider_monitor.py so form144_monitor.py (and any other
poller that needs to know "which users care about this ticker") can share
the exact same book-building logic without insider_monitor.py <-> that
poller becoming a circular import — insider_monitor.py already imports
from form144_monitor.py (get_recent_144_notice) for the sell-side
correlation note, so this had to live somewhere both can reach.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Portfolio, PortfolioPosition, Watchlist, WatchlistItem
from .briefing_advice import load_investment_rules
from .insider_gate import BookSnapshot, sector_exposure


def load_avoid_tickers() -> set:
    return {str(t).upper() for t in load_investment_rules().get("avoid_tickers", [])}


async def load_books(session: AsyncSession) -> tuple[dict, dict]:
    """Open positions + watchlist items -> one BookSnapshot per user who has
    either, keyed by user_id, plus a shared ticker->sector map (issuer-level
    metadata, not user-specific, so it's fine to pool across everyone's
    positions).

    Watchlist tickers get full gating parity with real holdings (a watchlist
    ticker's insider sell/buy alerts the same way a held position's would —
    the closest available signal for a "planned buy" alert, since unlike
    Form 144's real "planned sell" notice, there's no SEC filing that
    telegraphs an intended purchase) but are kept in a separate
    watchlist_tickers set, not folded into held_tickers or positions, so
    sector-exposure math and stop/phase advice stay scoped to real
    positions only — a watchlist ticker has no shares, cost basis, or entry
    date to compute those from.

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

    watchlist_res = await session.execute(
        select(WatchlistItem.symbol, Watchlist.user_id).join(
            Watchlist, Watchlist.watchlist_id == WatchlistItem.watchlist_id
        )
    )
    watchlist_by_user: dict = {}
    for symbol, uid in watchlist_res.all():
        t = (symbol or "").strip().upper()
        if t:
            watchlist_by_user.setdefault(uid, set()).add(t)

    avoid = load_avoid_tickers()
    all_user_ids = set(by_user.keys()) | set(watchlist_by_user.keys())
    books: dict = {}
    for uid in all_user_ids:
        user_positions = by_user.get(uid, [])
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
            watchlist_tickers=watchlist_by_user.get(uid, set()),
        )
    return books, sectors
