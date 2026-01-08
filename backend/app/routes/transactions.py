from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from ..db import get_db
from ..schemas import TransactionCreate, TransactionOut
from ..models import Transaction

router = APIRouter()

@router.post("/create", response_model=TransactionOut)
async def create_transaction(payload: TransactionCreate, db: AsyncSession = Depends(get_db)):
    # Authoritative server-side monetary operation with explicit transaction
    if payload.amount <= Decimal("0"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount must be positive")

    new = Transaction(
        account_id=payload.account_id,
        transaction_type=payload.transaction_type,
        amount=payload.amount,
        currency=payload.currency,
        status="pending"
    )

    async with db.begin():
        db.add(new)

    await db.refresh(new)
    return new
