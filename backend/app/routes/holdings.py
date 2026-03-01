"""
holdings.py — Holdings (portfolio positions) routes for TickerTap.

Exposes a paginated list of holdings per account, enforcing that the
requesting user owns the account (IDOR prevention).
"""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Holding
# Canonical auth dependency — returns a User ORM object
from .auth_routes import get_current_user

router = APIRouter()


class HoldingOut(BaseModel):
    """Output schema for a single holding position.

    Attributes:
        holding_id: Unique identifier for this position record.
        account_id: The account this holding belongs to.
        security_id: The tradeable security held.
        quantity: Number of shares/units held (up to 6 decimal places).
        average_cost: Average purchase price per unit (nullable).
        current_price: Most-recently-fetched market price (nullable).
    """

    holding_id: UUID
    account_id: UUID
    security_id: UUID
    quantity: Decimal
    average_cost: Optional[Decimal] = None
    current_price: Optional[Decimal] = None

    class Config:
        orm_mode = True


async def _assert_account_owner(account_id: UUID, user_id: UUID, db: AsyncSession) -> None:
    """Verify the account belongs to the given user. Raises HTTP 403 if not.

    Used to prevent Insecure Direct Object Reference (IDOR) attacks where a
    user could enumerate holdings of another user by guessing account UUIDs.

    Args:
        account_id: The account UUID to check ownership for.
        user_id: The authenticated user's UUID.
        db: The async database session.

    Raises:
        HTTPException(403): If the account does not exist or belongs to a
            different user.
    """
    result = await db.execute(
        select(Account).where(Account.account_id == account_id, Account.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Account not found or access denied")


@router.get("/", response_model=List[HoldingOut])
async def list_holdings(
    account_id: UUID = Query(..., description="Account UUID to list holdings for."),
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of holdings to return (1–100).",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of holdings to skip for pagination.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List holdings for the given account with pagination (P7.3).

    Ownership of the requested account is verified before returning data
    to prevent IDOR — users cannot enumerate holdings from accounts they
    do not own.

    Args:
        account_id: The account UUID to list holdings for.
        limit: Maximum results per page (1–100, default 50).
        offset: Number of records to skip (default 0).
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        List[HoldingOut] — holdings for the account (paginated).

    Raises:
        HTTPException(403): Account not found or not owned by current user.
    """
    # Ownership check — raises 403 if account belongs to another user
    await _assert_account_owner(account_id, current_user.user_id, db)
    result = await db.execute(
        select(Holding)
        .where(Holding.account_id == account_id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
