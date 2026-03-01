"""
transactions.py — Deposit/withdrawal routes for TickerTap.

All balance-mutating operations (deposits and withdrawals) execute inside a
single database transaction that holds a row-level lock (SELECT … FOR UPDATE)
on the account row for the duration of the operation.  This prevents
double-spend races when concurrent requests hit the same account simultaneously.

Transaction atomicity guarantee:
  1. Lock acquired  (SELECT … FOR UPDATE inside async with db.begin())
  2. Balance validated and updated
  3. Transaction record and audit log inserted
  4. Lock released on commit
If any step raises, the entire transaction is rolled back automatically.
"""

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models import Account, AuditLog, Transaction
from ..schemas import TransactionCreate, TransactionOut
from .auth_routes import get_current_user


router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("/create", response_model=TransactionOut)
async def create_transaction(
    payload: TransactionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a deposit or withdrawal on an account.

    The account row is locked with SELECT … FOR UPDATE inside the transaction
    block so that concurrent requests cannot read a stale balance before either
    one commits, preventing double-spend scenarios.

    Args:
        payload: TransactionCreate — amount, transaction_type, account_id, etc.
        request: FastAPI Request — used to capture IP for the audit log.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        TransactionOut — the newly created transaction record.

    Raises:
        HTTP 400 if amount is non-positive, transaction_type is unsupported,
                 or withdrawal would exceed current balance.
        HTTP 404 if account_id does not belong to current_user.
    """
    if payload.amount <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount must be positive",
        )

    # Everything below runs inside a single atomic transaction.
    # The SELECT … FOR UPDATE lock is acquired within this block, ensuring
    # the lock is held until the COMMIT, preventing concurrent balance reads.
    async with db.begin():
        # Lock the account row for the duration of this transaction.
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

        old_balance = account.balance or Decimal("0")

        if payload.transaction_type == "deposit":
            new_balance = old_balance + payload.amount
        elif payload.transaction_type == "withdrawal":
            if old_balance < payload.amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="insufficient funds",
                )
            new_balance = old_balance - payload.amount
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="unsupported transaction_type",
            )

        # Update the account balance atomically within the same transaction.
        await db.execute(
            update(Account)
            .where(Account.account_id == account.account_id)
            .values(balance=new_balance)
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

        audit = AuditLog(
            user_id=current_user.user_id,
            action="transaction_create",
            table_name="transactions",
            record_id=new_txn.transaction_id,
            old_values={"balance": str(old_balance)},
            new_values={
                "balance": str(new_balance),
                "transaction_type": payload.transaction_type,
                "amount": str(payload.amount),
                "currency": payload.currency,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        db.add(new_txn)
        db.add(audit)
    # Transaction committed here — lock released, balance change durable.

    await db.refresh(new_txn)
    return new_txn


@router.get("/", response_model=list[TransactionOut])
async def list_transactions(
    account_id: Optional[str] = Query(
        default=None,
        description="Filter by account_id; must belong to current user.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List transactions belonging to the current user.

    Args:
        account_id: Optional filter — only return transactions for this account.
        db: AsyncSession — injected database session.
        current_user: User — the authenticated user (from JWT).

    Returns:
        List[TransactionOut] — transactions ordered newest-first.
    """
    query = (
        select(Transaction)
        .join(Account, Transaction.account_id == Account.account_id)
        .where(Account.user_id == current_user.user_id)
    )
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    query = query.order_by(Transaction.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()
