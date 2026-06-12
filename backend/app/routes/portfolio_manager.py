"""
routes/portfolio_manager.py — Portfolio Manager API endpoints.

Provides CRUD for user-owned portfolios and their positions.
All endpoints require authentication.  Ownership is enforced by
verifying portfolio.user_id == current_user.user_id on every operation.

Route prefix: /api/v1/portfolio-manager  (registered in main.py)
"""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List
from uuid import UUID

import yfinance as yf
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition, PortfolioTrade
from ..schemas import (
    CashAdjustmentRequest,
    PerformancePointOut,
    PortfolioCreate,
    PortfolioOut,
    PortfolioTradeOut,
    PositionCreate,
    PositionOut,
    PositionUpdate,
    SellRequest,
)
from .auth_routes import get_current_user

router = APIRouter(prefix="/portfolio-manager", tags=["portfolio-manager"])


# ── Helper ───────────────────────────────────────────────────────────────────

async def _get_portfolio_or_404(
    portfolio_id: UUID,
    db: AsyncSession,
    current_user,
) -> Portfolio:
    """Load a portfolio and verify ownership; raise 404 if not found or not owned."""
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.portfolio_id == portfolio_id,
            Portfolio.user_id == current_user.user_id,
        )
    )
    portfolio = result.scalar_one_or_none()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found.")
    return portfolio


async def _get_position_or_404(
    position_id: UUID,
    db: AsyncSession,
    current_user,
) -> PortfolioPosition:
    """Load a position and verify ownership via portfolio join; raise 404 if not found."""
    result = await db.execute(
        select(PortfolioPosition)
        .join(Portfolio, Portfolio.portfolio_id == PortfolioPosition.portfolio_id)
        .where(
            PortfolioPosition.position_id == position_id,
            Portfolio.user_id == current_user.user_id,
        )
    )
    position = result.scalar_one_or_none()
    if position is None:
        raise HTTPException(status_code=404, detail="Position not found.")
    return position


# ── Portfolio endpoints ───────────────────────────────────────────────────────

@router.get("/portfolios", response_model=List[PortfolioOut])
async def list_portfolios(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all portfolios belonging to the authenticated user."""
    result = await db.execute(
        select(Portfolio)
        .where(Portfolio.user_id == current_user.user_id)
        .order_by(Portfolio.created_at)
    )
    return result.scalars().all()


@router.post("/portfolios", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
async def create_portfolio(
    payload: PortfolioCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new named portfolio for the authenticated user."""
    portfolio = Portfolio(
        user_id=current_user.user_id,
        name=payload.name,
        strategy=payload.strategy,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return portfolio


@router.delete("/portfolios/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_portfolio(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a portfolio and all its positions (CASCADE)."""
    portfolio = await _get_portfolio_or_404(portfolio_id, db, current_user)
    await db.delete(portfolio)
    await db.commit()


# ── Position endpoints ────────────────────────────────────────────────────────

@router.get("/portfolios/{portfolio_id}/positions", response_model=List[PositionOut])
async def list_positions(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all positions in a portfolio."""
    await _get_portfolio_or_404(portfolio_id, db, current_user)
    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.portfolio_id == portfolio_id)
        .order_by(PortfolioPosition.created_at)
    )
    return result.scalars().all()


@router.post(
    "/portfolios/{portfolio_id}/positions",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_position(
    portfolio_id: UUID,
    payload: PositionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Add a single position to a portfolio.

    When ``payload.deduct_cash`` is True, the position cost is subtracted from
    the portfolio's cash balance and a BUY trade record is created.  Returns 400
    if the portfolio has insufficient cash.
    """
    portfolio = await _get_portfolio_or_404(portfolio_id, db, current_user)

    if payload.deduct_cash:
        cost = float(payload.quantity * payload.purchase_price)
        if float(portfolio.cash_balance) < cost:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient cash balance. Available: ${float(portfolio.cash_balance):.2f}",
            )
        portfolio.cash_balance = float(portfolio.cash_balance) - cost
        trade = PortfolioTrade(
            portfolio_id=portfolio_id,
            trade_type="BUY",
            ticker=payload.ticker.strip().upper(),
            quantity=payload.quantity,
            price=payload.purchase_price,
            total_value=payload.quantity * payload.purchase_price,
        )
        db.add(trade)

    position = PortfolioPosition(
        portfolio_id=portfolio_id,
        ticker=payload.ticker.upper(),
        name=payload.name,
        quantity=payload.quantity,
        purchase_date=payload.purchase_date,
        purchase_price=payload.purchase_price,
        group_tag=payload.group_tag,
        asset_type=payload.asset_type,
        physical_type=payload.physical_type,
        hard_stop_loss=payload.hard_stop_loss,
        soft_stop_loss=payload.soft_stop_loss,
        profit_taking=payload.profit_taking,
    )


@router.post(
    "/portfolios/{portfolio_id}/import",
    response_model=List[PositionOut],
    status_code=status.HTTP_201_CREATED,
)
async def bulk_import_positions(
    portfolio_id: UUID,
    payload: List[PositionCreate],
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Bulk import positions into a portfolio. Returns created positions."""
    await _get_portfolio_or_404(portfolio_id, db, current_user)
    if not payload:
        raise HTTPException(status_code=400, detail="No positions provided.")
    if len(payload) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 positions per import.")

    positions = [
        PortfolioPosition(
            portfolio_id=portfolio_id,
            ticker=p.ticker.upper(),
            name=p.name,
            quantity=p.quantity,
            purchase_date=p.purchase_date,
            purchase_price=p.purchase_price,
            group_tag=p.group_tag,
            asset_type=p.asset_type,
            physical_type=p.physical_type,
            hard_stop_loss=p.hard_stop_loss,
            soft_stop_loss=p.soft_stop_loss,
            profit_taking=p.profit_taking,
        )
        for p in payload
    ]
    db.add_all(positions)
    await db.commit()
    for pos in positions:
        await db.refresh(pos)
    return positions


@router.patch("/positions/{position_id}", response_model=PositionOut)
async def modify_position(
    position_id: UUID,
    payload: PositionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update one or more fields of a position."""
    position = await _get_position_or_404(position_id, db, current_user)
    if payload.quantity is not None:
        position.quantity = payload.quantity
    if payload.purchase_price is not None:
        position.purchase_price = payload.purchase_price
    if payload.group_tag is not None:
        position.group_tag = payload.group_tag
    if payload.is_excluded is not None:
        position.is_excluded = payload.is_excluded
    if payload.hard_stop_loss is not None:
        position.hard_stop_loss = payload.hard_stop_loss if payload.hard_stop_loss > 0 else None
    if payload.soft_stop_loss is not None:
        position.soft_stop_loss = payload.soft_stop_loss if payload.soft_stop_loss > 0 else None
    if payload.profit_taking is not None:
        position.profit_taking = payload.profit_taking if payload.profit_taking > 0 else None
    await db.commit()
    await db.refresh(position)
    return position


@router.delete("/positions/{position_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a single position."""
    position = await _get_position_or_404(position_id, db, current_user)
    await db.delete(position)
    await db.commit()


@router.post("/positions/{position_id}/sell", response_model=PositionOut | None)
async def sell_position(
    position_id: UUID,
    payload: SellRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Partially or fully sell a position.

    - If sell quantity < current quantity: reduces quantity, returns updated position.
    - If sell quantity >= current quantity: deletes position, returns null.
    - When ``payload.credit_cash`` is True, the sale proceeds are added to the
      portfolio's cash balance and a SELL trade record is created.
    """
    position = await _get_position_or_404(position_id, db, current_user)

    # Load the parent portfolio for cash balance tracking
    port_result = await db.execute(
        select(Portfolio).where(Portfolio.portfolio_id == position.portfolio_id)
    )
    portfolio = port_result.scalar_one_or_none()

    # Use the provided sell price if supplied, otherwise fall back to purchase price
    sell_price = float(payload.sell_price) if payload.sell_price is not None else float(position.purchase_price)
    # Capture average cost basis at sell time for realized P&L calculation
    cost_basis = float(position.purchase_price)

    if payload.quantity >= position.quantity:
        # Fully sold — record quantity before deletion
        quantity_sold = float(position.quantity)
        sell_total = quantity_sold * sell_price

        # Always record the trade regardless of cash credit preference
        trade = PortfolioTrade(
            portfolio_id=position.portfolio_id,
            trade_type="SELL",
            ticker=position.ticker,
            quantity=Decimal(str(quantity_sold)),
            price=Decimal(str(sell_price)),
            cost_basis=Decimal(str(cost_basis)),
            total_value=Decimal(str(sell_total)),
        )
        db.add(trade)

        if payload.credit_cash and portfolio is not None:
            portfolio.cash_balance = float(portfolio.cash_balance) + sell_total

        await db.delete(position)
        await db.commit()
        return None

    # Partial sell
    quantity_sold = float(payload.quantity)
    sell_total = quantity_sold * sell_price
    position.quantity = Decimal(str(position.quantity)) - payload.quantity

    # Always record the trade regardless of cash credit preference
    trade = PortfolioTrade(
        portfolio_id=position.portfolio_id,
        trade_type="SELL",
        ticker=position.ticker,
        quantity=Decimal(str(quantity_sold)),
        price=Decimal(str(sell_price)),
        cost_basis=Decimal(str(cost_basis)),
        total_value=Decimal(str(sell_total)),
    )
    db.add(trade)

    if payload.credit_cash and portfolio is not None:
        portfolio.cash_balance = float(portfolio.cash_balance) + sell_total

    await db.commit()
    await db.refresh(position)
    return position


# ── Portfolio performance endpoint ────────────────────────────────────────────

def _compute_period_days(period: str, positions: list) -> int:
    """Convert a human-readable period code into a calendar-day count.

    Supported periods:
        "1W"  -> 7 days
        "1M"  -> 30 days
        "3M"  -> 90 days
        "YTD" -> days elapsed since January 1 of the current year
        "1Y"  -> 365 days
        "ALL" -> dynamically computed from the earliest purchase_date
                 across all positions to today

    Args:
        period: Period code string (e.g. "1W", "3M", "ALL").
        positions: List of PortfolioPosition ORM objects used for "ALL" range.

    Returns:
        Number of calendar days to look back.
    """
    today = date.today()

    if period == "1W":
        return 7
    if period == "1M":
        return 30
    if period == "3M":
        return 90
    if period == "YTD":
        jan1 = date(today.year, 1, 1)
        return (today - jan1).days or 1
    if period == "1Y":
        return 365
    if period == "ALL":
        # Derive the range dynamically from the earliest purchase_date
        earliest = today
        for pos in positions:
            if pos.purchase_date is not None:
                # purchase_date is DateTime(timezone=True); extract the date portion
                pd = pos.purchase_date.date() if isinstance(pos.purchase_date, datetime) else pos.purchase_date
                if pd < earliest:
                    earliest = pd
        return max((today - earliest).days, 1)

    # Fallback — treat unknown periods as 90 days
    return 90


def _fetch_ticker_histories(tickers: List[str], days: int) -> Dict[str, Dict[str, float]]:
    """Fetch daily close prices from yfinance for a list of tickers.

    This is a synchronous function intended to be called via
    ``asyncio.get_event_loop().run_in_executor`` because yfinance
    performs blocking HTTP requests internally.

    Args:
        tickers: Unique ticker symbols to fetch.
        days:    Number of calendar days of history to request.

    Returns:
        A dict mapping each ticker to an inner dict of
        ``{ "YYYY-MM-DD": close_price }`` entries.
    """
    ticker_data: Dict[str, Dict[str, float]] = {}

    for symbol in tickers:
        try:
            ticker_obj = yf.Ticker(symbol)
            hist = ticker_obj.history(period=f"{days}d")
            if hist.empty:
                continue
            # Build date -> close price mapping
            date_to_close: Dict[str, float] = {}
            for dt, row in hist.iterrows():
                date_str = dt.strftime("%Y-%m-%d")
                close = float(row["Close"])
                date_to_close[date_str] = round(close, 2)
            ticker_data[symbol] = date_to_close
        except Exception:
            # Skip tickers that fail (delisted, network errors, etc.)
            continue

    return ticker_data


def _build_performance_series(
    ticker_data: Dict[str, Dict[str, float]],
    positions: list,
) -> List[dict]:
    """Build a forward-filled portfolio value time series.

    For each calendar date present in any ticker's OHLCV data:
    1. Forward-fill missing closes (carry the last known price into gaps
       caused by weekends, holidays, or differing trading calendars).
    2. Sum ``quantity * close`` for every position whose purchase_date
       is on or before that date.

    Args:
        ticker_data: Per-ticker date-to-close maps from ``_fetch_ticker_histories``.
        positions:   Non-excluded PortfolioPosition ORM objects.

    Returns:
        A list of ``{"date": "YYYY-MM-DD", "value": float}`` dicts sorted
        by date ascending.
    """
    if not ticker_data:
        return []

    # ── Collect and sort all unique dates across every ticker ─────────────
    all_dates = sorted({d for closes in ticker_data.values() for d in closes})
    if not all_dates:
        return []

    # ── Forward-fill: for each ticker, carry the last known close into
    #    dates where no data exists (weekends, holidays, different markets) ─
    filled: Dict[str, Dict[str, float]] = {}
    for symbol, closes in ticker_data.items():
        filled[symbol] = {}
        last_close = None
        for d in all_dates:
            if d in closes:
                last_close = closes[d]
            if last_close is not None:
                filled[symbol][d] = last_close

    # ── Prepare position list with parsed purchase dates ─────────────────
    pos_list = []
    for pos in positions:
        pd = "1970-01-01"
        if pos.purchase_date is not None:
            if isinstance(pos.purchase_date, datetime):
                pd = pos.purchase_date.strftime("%Y-%m-%d")
            else:
                pd = str(pos.purchase_date)
        pos_list.append({
            "ticker": pos.ticker,
            "qty": float(pos.quantity),
            "purchase_date": pd,
        })

    # ── Build the time series ────────────────────────────────────────────
    series: List[dict] = []
    for d in all_dates:
        total = 0.0
        has_data = False
        for p in pos_list:
            # Only include positions that were purchased on or before this date
            if p["purchase_date"] > d:
                continue
            close = filled.get(p["ticker"], {}).get(d)
            if close is not None:
                total += p["qty"] * close
                has_data = True
        if has_data:
            series.append({"date": d, "value": round(total, 2)})

    return series


@router.get("/{portfolio_id}/trades", response_model=List[PortfolioTradeOut])
async def get_portfolio_trades(
    portfolio_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return all trade records for a portfolio, newest first.

    Args:
        portfolio_id: UUID of the target portfolio.
        db:           Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        List of PortfolioTradeOut objects sorted by created_at descending.

    Raises:
        HTTPException 404: If the portfolio does not exist or is not owned by
        the authenticated user.
    """
    await _get_portfolio_or_404(portfolio_id, db, current_user)
    result = await db.execute(
        select(PortfolioTrade)
        .where(PortfolioTrade.portfolio_id == portfolio_id)
        .order_by(PortfolioTrade.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/trades/{trade_id}", status_code=204)
async def delete_trade(
    trade_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete a trade record. Validates ownership via parent portfolio.

    Args:
        trade_id:     UUID of the trade to delete.
        db:           Async database session (injected).
        current_user: Authenticated user (injected).

    Raises:
        HTTPException 404: If the trade does not exist or is not owned by
        the authenticated user (verified by joining through the parent portfolio).
    """
    # Join trade -> portfolio to verify the authenticated user owns this record.
    result = await db.execute(
        select(PortfolioTrade)
        .join(Portfolio, PortfolioTrade.portfolio_id == Portfolio.portfolio_id)
        .where(PortfolioTrade.trade_id == trade_id)
        .where(Portfolio.user_id == current_user.user_id)
    )
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    await db.delete(trade)
    await db.commit()


@router.post("/{portfolio_id}/cash")
async def adjust_cash(
    portfolio_id: UUID,
    request: CashAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Manually adjust the cash balance of a portfolio.

    Positive amounts add cash (e.g. depositing funds); negative amounts
    subtract cash (e.g. recording an external expense).  Returns 400 if the
    adjustment would result in a negative balance.

    Args:
        portfolio_id: UUID of the target portfolio.
        request:      Amount and optional notes.
        db:           Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        Updated cash balance as JSON ``{ "cash_balance": float }``.

    Raises:
        HTTPException 400: If the resulting balance would be negative.
        HTTPException 404: Portfolio not found or not owned by user.
    """
    portfolio = await _get_portfolio_or_404(portfolio_id, db, current_user)

    new_balance = float(portfolio.cash_balance) + request.amount
    if new_balance < 0:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient funds. Current balance: ${float(portfolio.cash_balance):.2f}",
        )

    portfolio.cash_balance = new_balance
    await db.commit()
    return {"cash_balance": new_balance}


@router.get("/{portfolio_id}/performance", response_model=List[PerformancePointOut])
async def get_portfolio_performance(
    portfolio_id: UUID,
    period: str = Query("3M", description="Time range: 1W, 1M, 3M, YTD, 1Y, ALL"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Compute a daily portfolio value time series over the requested period.

    The endpoint:
    1. Verifies portfolio ownership.
    2. Loads all non-excluded positions for the portfolio.
    3. Fetches daily OHLCV data from yfinance for each unique ticker.
    4. Applies forward-fill so that weekends and holidays carry the last
       known close forward (no gaps in the series).
    5. For "ALL" period, dynamically determines the start date from the
       earliest purchase_date across all positions.
    6. Returns the resulting time series as a list of
       ``{date, value}`` points.

    Args:
        portfolio_id: UUID of the target portfolio.
        period:       Time range code — one of 1W, 1M, 3M, YTD, 1Y, ALL.
        db:           Async database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        List of PerformancePointOut objects sorted by date ascending.
    """
    # ── Validate period parameter ────────────────────────────────────────
    valid_periods = {"1W", "1M", "3M", "YTD", "1Y", "ALL"}
    if period not in valid_periods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period '{period}'. Valid values: {sorted(valid_periods)}",
        )

    # ── Verify portfolio ownership ───────────────────────────────────────
    await _get_portfolio_or_404(portfolio_id, db, current_user)

    # ── Load non-excluded positions ──────────────────────────────────────
    result = await db.execute(
        select(PortfolioPosition).where(
            PortfolioPosition.portfolio_id == portfolio_id,
            PortfolioPosition.is_excluded.is_(False),
        )
    )
    positions = result.scalars().all()

    # Edge case: no positions → return an empty series
    if not positions:
        return []

    # ── Compute day count from the period code ───────────────────────────
    days = _compute_period_days(period, positions)

    # ── Extract unique tickers from the positions ────────────────────────
    tickers = list({pos.ticker for pos in positions})

    # ── Fetch OHLCV history for each ticker (yfinance is synchronous,
    #    so we delegate to a thread pool to avoid blocking the event loop) ─
    loop = asyncio.get_event_loop()
    ticker_data: Dict[str, Dict[str, float]] = await loop.run_in_executor(
        None, _fetch_ticker_histories, tickers, days
    )

    # Edge case: no OHLCV data returned for any ticker
    if not ticker_data:
        return []

    # ── Build the forward-filled portfolio value time series ─────────────
    series = _build_performance_series(ticker_data, positions)

    return [PerformancePointOut(**point) for point in series]
