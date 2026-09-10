"""
Internal portfolio API — machine-to-machine only.

Exposes portfolio positions, summary, and watchlist to trusted internal
services (e.g. swarm-api) using the shared X-Internal-Key secret.
No JWT auth; no user scope. Returns aggregate data across all users.

Queries portfolio_positions (portfolio-manager module) — this is the table
that actually contains user holdings. The accounts/holdings tables are empty
in production; all real positions live in PortfolioPosition.
"""
import asyncio
import hmac
import logging
import os
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition, Watchlist, WatchlistItem
from .insider import list_all_filings, list_filings
from .market import _fetch_quote, _get_cached, _quote_ttl, _set_cached

router = APIRouter(prefix="/internal/portfolio", tags=["internal"])

logger = logging.getLogger(__name__)

_INTERNAL_NEWS_KEY = os.getenv("INTERNAL_NEWS_KEY", "")
_ALLOWED_WORKER_IP = os.getenv("WORKER_IP", "")


def _verify_internal_auth(request: Request) -> None:
    if not _INTERNAL_NEWS_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    provided_key = request.headers.get("X-Internal-Key", "")
    if not hmac.compare_digest(provided_key, _INTERNAL_NEWS_KEY):
        logger.warning(
            "Internal portfolio endpoint: invalid key from %s", request.client.host
        )
        raise HTTPException(status_code=403, detail="Forbidden")
    if _ALLOWED_WORKER_IP and request.client.host != _ALLOWED_WORKER_IP:
        logger.warning(
            "Internal portfolio endpoint: rejected IP %s (expected %s)",
            request.client.host,
            _ALLOWED_WORKER_IP,
        )
        raise HTTPException(status_code=403, detail="Forbidden")


class InternalPositionOut(BaseModel):
    symbol: str
    name: Optional[str] = None
    quantity: Decimal
    purchase_price: Decimal
    hard_stop_loss: Optional[Decimal] = None
    profit_taking: Optional[Decimal] = None
    sector: Optional[str] = None
    asset_type: str = "stock"
    is_excluded: bool = False

    class Config:
        orm_mode = True


class InternalPortfolioSummaryOut(BaseModel):
    total_cash_balance: Decimal
    currency: str = "USD"
    position_count: int
    portfolio_count: int


class InternalWatchlistSymbolOut(BaseModel):
    symbol: str
    asset_type: str
    notes: Optional[str] = None

    class Config:
        orm_mode = True


@router.get("/positions", response_model=List[InternalPositionOut])
async def internal_portfolio_positions(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """All active portfolio positions across all users."""
    _verify_internal_auth(request)

    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.is_excluded == False)  # noqa: E712
        .order_by(PortfolioPosition.ticker.asc())
    )
    positions = result.scalars().all()

    return [
        InternalPositionOut(
            symbol=p.ticker,
            name=p.name,
            quantity=p.quantity,
            purchase_price=p.purchase_price,
            hard_stop_loss=p.hard_stop_loss,
            profit_taking=p.profit_taking,
            sector=p.sector,
            asset_type=p.asset_type,
            is_excluded=p.is_excluded,
        )
        for p in positions
    ]


@router.get("/summary", response_model=InternalPortfolioSummaryOut)
async def internal_portfolio_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate portfolio summary across all portfolios."""
    _verify_internal_auth(request)

    portfolios_result = await db.execute(select(Portfolio))
    portfolios = portfolios_result.scalars().all()
    total_cash = sum(p.cash_balance or Decimal("0") for p in portfolios)

    positions_result = await db.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.is_excluded == False  # noqa: E712
        )
    )
    positions = positions_result.scalars().all()

    return InternalPortfolioSummaryOut(
        total_cash_balance=total_cash,
        currency="USD",
        position_count=len(positions),
        portfolio_count=len(portfolios),
    )


@router.get("/watchlist", response_model=List[InternalWatchlistSymbolOut])
async def internal_watchlist(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """All watchlist items across all users."""
    _verify_internal_auth(request)

    result = await db.execute(
        select(WatchlistItem).order_by(WatchlistItem.symbol.asc())
    )
    items = result.scalars().all()

    return [
        InternalWatchlistSymbolOut(
            symbol=item.symbol,
            asset_type=item.asset_type,
            notes=item.notes,
        )
        for item in items
    ]


# ── Kamilo endpoints ──────────────────────────────────────────────────────────
# Same "trusted internal service, no user scope" model as above, but with a
# dedicated secret (KAMILO_SERVICE_KEY, not INTERNAL_NEWS_KEY) so rotating or
# revoking Kamilo's access can never affect the news worker or vice versa.
# These add what the endpoints above don't have: live prices/P&L, an
# any-ticker quote lookup, and insider-filing alerts — so Kamilo can answer
# "what's my portfolio worth" / "what's NVDA at" / "any insider activity"
# style questions, not just report cost-basis positions.

_KAMILO_SERVICE_KEY = os.getenv("KAMILO_SERVICE_KEY", "")


def _verify_kamilo_auth(request: Request) -> None:
    if not _KAMILO_SERVICE_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")
    provided_key = request.headers.get("X-Kamilo-Key", "")
    if not hmac.compare_digest(provided_key, _KAMILO_SERVICE_KEY):
        logger.warning(
            "Internal Kamilo endpoint: invalid key from %s", request.client.host
        )
        raise HTTPException(status_code=403, detail="Forbidden")


async def _quote_cached(sym: str):
    """Same cache the public /market/quote endpoint uses — never doubles yfinance load."""
    sym = sym.upper()
    cache_key = f"quote:{sym}"
    cached = _get_cached(cache_key, _quote_ttl())
    if cached:
        return cached
    quote = await asyncio.to_thread(_fetch_quote, sym)
    _set_cached(cache_key, quote)
    return quote


class KamiloPositionOut(BaseModel):
    ticker: str
    quantity: float
    purchase_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class KamiloPortfolioOut(BaseModel):
    portfolio_id: str
    name: str
    cash_balance: float
    positions_value: float
    total_value: float
    positions: List[KamiloPositionOut]


class KamiloPortfolioResponse(BaseModel):
    portfolios: List[KamiloPortfolioOut]
    total_value_all_portfolios: float
    total_cash_all_portfolios: float


class KamiloWatchlistItemOut(BaseModel):
    symbol: str
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    price_when_added: Optional[float] = None


class KamiloWatchlistOut(BaseModel):
    name: str
    items: List[KamiloWatchlistItemOut]


class KamiloWatchlistResponse(BaseModel):
    watchlists: List[KamiloWatchlistOut]


class KamiloAlertsResponse(BaseModel):
    tracked_tickers: List[str]
    form4: List[dict]
    other_filings: List[dict]


@router.get("/kamilo/live", response_model=KamiloPortfolioResponse)
async def kamilo_portfolio_live(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Every portfolio's positions priced live, plus per-portfolio and grand totals."""
    _verify_kamilo_auth(request)

    result = await db.execute(select(Portfolio))
    portfolios = result.scalars().all()

    out = []
    grand_total = 0.0
    grand_cash = 0.0
    for p in portfolios:
        pos_result = await db.execute(
            select(PortfolioPosition).where(
                PortfolioPosition.portfolio_id == p.portfolio_id,
                PortfolioPosition.is_excluded == False,  # noqa: E712
            )
        )
        positions = pos_result.scalars().all()
        pos_out = []
        positions_value = 0.0
        for pos in positions:
            cost = float(pos.purchase_price)
            try:
                quote = await _quote_cached(pos.ticker)
                price = quote.price
            except Exception:
                price = cost
            qty = float(pos.quantity)
            market_value = round(price * qty, 2)
            positions_value += market_value
            pos_out.append(KamiloPositionOut(
                ticker=pos.ticker,
                quantity=qty,
                purchase_price=cost,
                current_price=price,
                market_value=market_value,
                unrealized_pnl=round((price - cost) * qty, 2),
                unrealized_pnl_pct=round((price - cost) / cost * 100, 2) if cost else 0.0,
            ))
        cash = float(p.cash_balance or 0)
        grand_cash += cash
        grand_total += positions_value + cash
        out.append(KamiloPortfolioOut(
            portfolio_id=str(p.portfolio_id),
            name=p.name,
            cash_balance=cash,
            positions_value=round(positions_value, 2),
            total_value=round(positions_value + cash, 2),
            positions=pos_out,
        ))

    return KamiloPortfolioResponse(
        portfolios=out,
        total_value_all_portfolios=round(grand_total, 2),
        total_cash_all_portfolios=round(grand_cash, 2),
    )


@router.get("/kamilo/watchlist-live", response_model=KamiloWatchlistResponse)
async def kamilo_watchlist_live(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """All watchlists with a live quote per symbol (the /watchlist endpoint
    above has no pricing — this is what a chat query actually needs)."""
    _verify_kamilo_auth(request)

    wl_result = await db.execute(select(Watchlist))
    watchlists = wl_result.scalars().all()
    out = []
    for wl in watchlists:
        item_result = await db.execute(
            select(WatchlistItem).where(WatchlistItem.watchlist_id == wl.watchlist_id)
        )
        items = item_result.scalars().all()
        item_out = []
        for it in items:
            try:
                quote = await _quote_cached(it.symbol)
                price, change_pct = quote.price, quote.change_pct
            except Exception:
                price, change_pct = None, None
            item_out.append(KamiloWatchlistItemOut(
                symbol=it.symbol,
                current_price=price,
                change_pct=change_pct,
                price_when_added=float(it.price_when_added) if it.price_when_added else None,
            ))
        out.append(KamiloWatchlistOut(name=wl.name, items=item_out))
    return KamiloWatchlistResponse(watchlists=out)


@router.get("/kamilo/quote/{ticker}")
async def kamilo_quote(ticker: str, request: Request):
    """Live quote for any ticker — not account-scoped, just a convenience
    passthrough so Kamilo doesn't need a second market-data source."""
    _verify_kamilo_auth(request)
    try:
        return await _quote_cached(ticker)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Could not fetch quote for '{ticker}': {exc}")


@router.get("/kamilo/alerts", response_model=KamiloAlertsResponse)
async def kamilo_alerts(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Recent insider activity — Form 4 plus every other filing type (144/3/
    13D/13G/8-K/13F) — filtered to tickers actually held or watchlisted,
    the same scope the alerting pipeline itself uses (see insider_gate.py)."""
    _verify_kamilo_auth(request)

    pos_result = await db.execute(
        select(PortfolioPosition.ticker).where(PortfolioPosition.is_excluded == False)  # noqa: E712
    )
    wl_result = await db.execute(select(WatchlistItem.symbol))
    tracked = {t.upper() for (t,) in pos_result.all() if t} | {s.upper() for (s,) in wl_result.all() if s}

    # Called directly as plain functions, not through FastAPI's request
    # pipeline — every Query(...)-defaulted param must be passed explicitly,
    # since bypassing FastAPI's DI leaves unpassed ones as raw Query objects
    # rather than their resolved default values.
    form4 = await list_filings(
        ticker=None, owner_cik=None, code=None, days=days,
        sort="transaction_date", order="desc", limit=100, offset=0, db=db,
    )
    other = await list_all_filings(
        ticker=None, source="all", days=days,
        sort="date", order="desc", limit=100, offset=0, db=db,
    )

    def _tracked(ticker: Optional[str]) -> bool:
        return not tracked or (ticker or "").upper() in tracked

    return KamiloAlertsResponse(
        tracked_tickers=sorted(tracked),
        form4=[f.dict() for f in form4.items if _tracked(f.ticker)],
        other_filings=[f.dict() for f in other.items if _tracked(f.ticker)],
    )
