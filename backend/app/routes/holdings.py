from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from ..db import get_db
from ..models import Holding, Account
# Canonical auth dependency — returns a User ORM object
from .auth_routes import get_current_user

router = APIRouter()


class HoldingOut(BaseModel):
    holding_id: UUID
    account_id: UUID
    security_id: UUID
    quantity: Decimal
    average_cost: Optional[Decimal]
    current_price: Optional[Decimal]

    class Config:
        orm_mode = True


async def _assert_account_owner(account_id: UUID, user_id, db: AsyncSession):
    """Verify the account belongs to the given user. Raises 403 if not.

    Args:
        account_id: The account UUID to check.
        user_id: The user UUID (accepts both UUID and string).
        db: The async database session.
    """
    result = await db.execute(
        select(Account).where(Account.account_id == account_id, Account.user_id == user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Account not found or access denied")


@router.get("/", response_model=List[HoldingOut])
async def list_holdings(account_id: UUID, db: AsyncSession = Depends(get_db),
                        current_user=Depends(get_current_user)):
    # current_user is now a User ORM object; pass .user_id for comparison
    await _assert_account_owner(account_id, current_user.user_id, db)
    result = await db.execute(select(Holding).where(Holding.account_id == account_id))
    return result.scalars().all()
