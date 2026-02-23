from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account
from ..schemas import AccountCreate, AccountOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Very simple account number generation; rely on DB uniqueness constraint
    account_number = uuid4().hex[:12]

    account = Account(
        user_id=current_user.user_id,
        account_type=payload.account_type,
        account_number=account_number,
        currency=payload.currency,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.get("/me", response_model=list[AccountOut])
async def list_my_accounts(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    result = await db.execute(
        select(Account).where(Account.user_id == current_user.user_id)
    )
    accounts = result.scalars().all()
    return accounts

