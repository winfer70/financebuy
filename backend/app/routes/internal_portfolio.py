"""
Internal portfolio API — machine-to-machine only.

Exposes portfolio positions, summary, and watchlist to trusted internal
services (e.g. swarm-api) using the shared X-Internal-Key secret.
No JWT auth; no user scope. Returns aggregate data across all users.

Queries portfolio_positions (portfolio-manager module) — this is the table
that actually contains user holdings. The accounts/holdings tables are empty
in production; all real positions live in PortfolioPosition.
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
from ..models import Portfolio, PortfolioPosition, WatchlistItem

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
    stop_loss: Optional[Decimal] = None
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
            stop_loss=p.stop_loss,
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
