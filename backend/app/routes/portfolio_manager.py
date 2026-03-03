"""
routes/portfolio_manager.py — Portfolio Manager API endpoints.

Provides CRUD for user-owned portfolios and their positions.
All endpoints require authentication.  Ownership is enforced by
verifying portfolio.user_id == current_user.user_id on every operation.

Route prefix: /api/v1/portfolio-manager  (registered in main.py)
"""

from decimal import Decimal
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Portfolio, PortfolioPosition
from ..schemas import (
    PortfolioCreate,
    PortfolioOut,
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
    """Add a single position to a portfolio."""
    await _get_portfolio_or_404(portfolio_id, db, current_user)
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
        stop_loss=payload.stop_loss,
    )
    db.add(position)
    await db.commit()
    await db.refresh(position)
    return position


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
            stop_loss=p.stop_loss,
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
    if payload.stop_loss is not None:
        position.stop_loss = payload.stop_loss if payload.stop_loss > 0 else None
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
    - If sell quantity >= current quantity: deletes position, returns null (HTTP 204 would
      prevent the frontend from knowing the row is gone, so we return 200 with null body).
    """
    position = await _get_position_or_404(position_id, db, current_user)

    if payload.quantity >= position.quantity:
        # Fully sold — remove the row
        await db.delete(position)
        await db.commit()
        return None

    position.quantity = Decimal(str(position.quantity)) - payload.quantity
    await db.commit()
    await db.refresh(position)
    return position
