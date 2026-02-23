from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, AuditLog
from ..schemas import AccountCreate, AccountOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate,
    request: Request,
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

    audit = AuditLog(
        user_id=current_user.user_id,
        action="account_create",
        table_name="accounts",
        record_id=account.account_id,
        old_values=None,
        new_values={
            "account_type": account.account_type,
            "currency": account.currency,
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.add(account)
    db.add(audit)
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

