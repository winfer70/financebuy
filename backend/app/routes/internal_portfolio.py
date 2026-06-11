"""
Internal portfolio API — machine-to-machine only.

Exposes portfolio positions, summary, and watchlist to trusted internal
services (e.g. swarm-api) using the shared X-Internal-Key secret.
No JWT auth; no user scope. Returns aggregate data across all users.
"""
import hmac
import logging
import os
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Holding, Security, Watchlist, WatchlistItem

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
    name: str
    quantity: Decimal
    average_cost: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    market_value: Decimal
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_pct: Optional[Decimal] = None
    currency: str
    security_type: str

    class Config:
        orm_mode = True


class InternalPortfolioSummaryOut(BaseModel):
    total_portfolio_value: Decimal
    total_positions_value: Decimal
    total_cash_balance: Decimal
    currency: str = "USD"
    position_count: int


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
    """All held positions across all users with live prices and P&L."""
    _verify_internal_auth(request)

    result = await db.execute(
        select(Holding, Security).join(
            Security, Holding.security_id == Security.security_id
        )
    )

    positions: List[InternalPositionOut] = []
    for holding, security in result.all():
        qty = holding.quantity or Decimal("0")
        price = holding.current_price or Decimal("0")
        market_value = qty * price

        unrealized_pnl: Optional[Decimal] = None
        unrealized_pnl_pct: Optional[Decimal] = None
        if holding.average_cost and price:
            unrealized_pnl = (price - holding.average_cost) * qty
            if holding.average_cost != 0:
                unrealized_pnl_pct = (
                    (price - holding.average_cost) / holding.average_cost * 100
                )

        positions.append(
            InternalPositionOut(
                symbol=security.symbol,
                name=security.name,
                quantity=qty,
                average_cost=holding.average_cost,
                current_price=holding.current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_pct=unrealized_pnl_pct,
                currency=security.currency,
                security_type=security.security_type,
            )
        )

    return positions


@router.get("/summary", response_model=InternalPortfolioSummaryOut)
async def internal_portfolio_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Aggregate portfolio value across all accounts."""
    _verify_internal_auth(request)

    accounts_result = await db.execute(select(Account))
    accounts = accounts_result.scalars().all()
    total_cash = sum(a.balance or Decimal("0") for a in accounts)

    holdings_result = await db.execute(
        select(Holding, Security).join(
            Security, Holding.security_id == Security.security_id
        )
    )
    rows = holdings_result.all()

    total_positions = sum(
        (h.quantity or Decimal("0")) * (h.current_price or Decimal("0"))
        for h, _ in rows
    )

    return InternalPortfolioSummaryOut(
        total_portfolio_value=total_cash + total_positions,
        total_positions_value=total_positions,
        total_cash_balance=total_cash,
        currency="USD",
        position_count=len(rows),
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
