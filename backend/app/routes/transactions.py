from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, Transaction
from ..schemas import TransactionCreate, TransactionOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/create", response_model=TransactionOut)
async def create_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Authoritative server-side monetary operation with explicit transaction
    if payload.amount <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be positive",
        )

    # Load and lock the account row for update
    result = await db.execute(
        select(Account)
        .where(
            Account.account_id == payload.account_id,
            Account.user_id == current_user.user_id,
        )
        .with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="account not found",
        )

    new_balance = account.balance
    if payload.transaction_type == "deposit":
        new_balance = (new_balance or Decimal("0")) + payload.amount
    elif payload.transaction_type == "withdrawal":
        current = new_balance or Decimal("0")
        if current < payload.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="insufficient funds",
            )
        new_balance = current - payload.amount
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="unsupported transaction_type",
        )

    new_txn = Transaction(
        account_id=payload.account_id,
        transaction_type=payload.transaction_type,
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        reference_number=payload.reference_number,
        status="completed",
    )

    async with db.begin():
        await db.execute(
            update(Account)
            .where(Account.account_id == account.account_id)
            .values(balance=new_balance)
        )
        db.add(new_txn)

    await db.refresh(new_txn)
    return new_txn
